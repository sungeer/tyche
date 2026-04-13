"""
Node2：合规拦截 + Skill 路由
全部为纯代码逻辑，不调用 LLM。

执行顺序：
  Step1 权限检查 → Step2 风险等级检查 → Step3 人工审核规则 → Step4 Skill 路由
"""
import time
from datetime import datetime, timezone, timedelta

import httpx
import jsonschema
from loguru import logger

from src.core.config import settings
from src.core.db import engine
from src.core.exceptions import BadRequestError
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import repository
from src.domains.agent.routing import (
    INTENT_PERMISSION_MAP,
    INTENT_SKILL_MAP,
    REVIEW_RULE_MAP,
)
from src.domains.agent.skill_registry import SKILL_REGISTRY
from src.domains.agent.state import (
    append_node_trace,
    append_compliance_event,
    now_utc,
)

# 涉及客户-产品匹配度检查的意图（需做风险等级合规检查）
_RISK_CHECK_INTENTS = frozenset({'portfolio_analysis', 'redemption_initiate'})


def _check_permission(user_roles, intent_category):
    """
    Step1：权限检查。
    返回 (passed: bool, deny_reason: str)。
    """
    required = INTENT_PERMISSION_MAP.get(intent_category)
    if required is None:
        return True, ''
    if required in user_roles:
        return True, ''
    return False, f'当前角色无权执行"{intent_category}"操作，需要权限：{required}'


async def _check_risk_level(user_id, customer_id, product_id):
    """
    Step2：调用行内风控规则引擎，检查客户风险等级与产品风险等级的合规性。
    返回 (passed: bool, reason: str)。
    """
    if not customer_id or not product_id:
        return True, ''

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f'{settings.risk_engine_url}/v1/compliance/risk-match',
                json={
                    'user_id': user_id,
                    'customer_id': customer_id,
                    'product_id': product_id,
                },
                headers={'X-Api-Key': settings.risk_engine_api_key},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get('passed'):
                reason = data.get('reason', '客户风险等级与产品风险等级不匹配')
                return False, reason
            return True, ''
    except httpx.RequestError as e:
        # 风控引擎不可用时：出于安全考虑，拒绝操作
        logger.error(f'[Node2] 风控引擎调用失败：{e}')
        return False, '风控合规服务暂时不可用，操作已被拒绝'


async def _check_human_review(intent_category, entities, user_id):
    """
    Step3：检查是否需要触发人工审核。
    返回匹配的审核规则（或 None）。
    """
    # 规则1：赎回金额 >= 50 万
    if intent_category == 'redemption_initiate':
        amount = entities.get('amount')
        if amount and float(amount) >= 500000:
            return REVIEW_RULE_MAP.get('redemption_large_amount')

    # 规则3：同一顾问同日内 >= 3 次访问持仓（含 portfolio_analysis / risk_assessment）
    # 注：因 customer_id 未单独落库，统计当日全量持仓访问次数（保守近似）
    if intent_category in ('portfolio_analysis', 'risk_assessment'):
        rule = REVIEW_RULE_MAP.get('frequent_portfolio_access')
        if rule:
            today = datetime.now(timezone.utc).date()
            day_start = f'{today} 00:00:00.000'
            day_end = f'{today + timedelta(days=1)} 00:00:00.000'

            def count_sync():
                with engine.connect() as conn:
                    return repository.count_portfolio_access_today(
                        conn, user_id, day_start, day_end,
                    )

            access_count = await run_in_threadpool(db_threadpool, count_sync)
            if access_count >= 3:
                return rule

    return None


def _build_skill_params(skill_id, entities, prev_skill_results):
    """
    从 intent.entities 自动映射 Skill 入参。
    对于有依赖的 Skill（depends_on 非空），从前置 Skill 的结果注入数据。
    """
    params = {}
    meta = SKILL_REGISTRY[skill_id]

    # 通用字段映射：entities 中的字段直接传入
    field_map = {
        'product_id': entities.get('product_id'),
        'product_name': entities.get('product_name'),
        'customer_id': _to_int(entities.get('customer_id')),
        'amount': _to_float(entities.get('amount')),
        'start_date': entities.get('start_date'),
        'end_date': entities.get('end_date'),
        'scenario': entities.get('scenario'),
    }
    for k, v in field_map.items():
        if v is not None:
            params[k] = v

    # 依赖注入：run_stress_test 需要 portfolio_snapshot
    if skill_id == 'run_stress_test' and prev_skill_results:
        for result in prev_skill_results:
            if result['skill_id'] == 'query_customer_portfolio' and result['status'] == 'ok':
                params['portfolio_snapshot'] = result['data']
                break

    return params


def _validate_params(skill_id, params):
    """用 SKILL_REGISTRY 中的 params_schema 做 JSON Schema 校验"""
    schema = SKILL_REGISTRY[skill_id]['params_schema']
    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.ValidationError as e:
        raise BadRequestError(f'Skill [{skill_id}] 参数校验失败：{e.message}')


def _to_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _to_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def run(state):
    """Node2 入口：合规拦截 + Skill 路由"""
    started_at = now_utc()
    t0 = time.monotonic()

    user = state['input']['user']
    intent = state['working']['intent']
    intent_category = intent['category']
    entities = intent.get('entities', {})

    # 初始化 route 结构
    state['working']['route'] = {
        'selected_skills': [],
        'compliance': {
            'passed': True,
            'events': [],
        },
        'human_review': {
            'required': False,
            'reason': None,
            'rule_id': None,
            'assign_to_role': None,
            'sla_hours': None,
        },
    }

    try:
        # --------------------------------------------------
        # Step1：权限检查
        # --------------------------------------------------
        passed, deny_reason = _check_permission(user['roles'], intent_category)
        if not passed:
            append_compliance_event(
                state,
                event_type='permission_check',
                result='blocked',
                rule_id='permission_matrix',
                detail=deny_reason,
            )
            state['working']['route']['compliance']['passed'] = False
            state['working']['response'] = {'text': deny_reason, 'validation': {}, 'token_usage': {}}
            append_node_trace(state, 'node2_compliance_gate', started_at, 'ok',
                              f'权限拦截：{deny_reason}')
            return state

        append_compliance_event(
            state,
            event_type='permission_check',
            result='passed',
            rule_id='permission_matrix',
            detail=f'角色 {user["roles"]} 有权执行 {intent_category}',
        )

        # --------------------------------------------------
        # Step2：风险等级检查（仅特定意图）
        # --------------------------------------------------
        if intent_category in _RISK_CHECK_INTENTS:
            customer_id = entities.get('customer_id')
            product_id = entities.get('product_id')

            if customer_id and product_id:
                passed, deny_reason = await _check_risk_level(
                    user['user_id'],
                    customer_id,
                    product_id,
                )
                event_result = 'passed' if passed else 'blocked'
                append_compliance_event(
                    state,
                    event_type='risk_level_check',
                    result=event_result,
                    rule_id='risk_match_rule',
                    detail=deny_reason or '风险等级匹配',
                )
                if not passed:
                    state['working']['route']['compliance']['passed'] = False
                    state['working']['response'] = {'text': deny_reason, 'validation': {}, 'token_usage': {}}
                    append_node_trace(state, 'node2_compliance_gate', started_at, 'ok',
                                      f'合规拦截：{deny_reason}')
                    return state

        # --------------------------------------------------
        # Step3：人工审核规则检查
        # --------------------------------------------------
        review_rule = await _check_human_review(intent_category, entities, user['user_id'])
        if review_rule:
            state['working']['route']['human_review'] = {
                'required': True,
                'reason': review_rule['description'],
                'rule_id': review_rule['rule_id'],
                'assign_to_role': review_rule['assign_to_role'],
                'sla_hours': review_rule['sla_hours'],
            }
            append_compliance_event(
                state,
                event_type='rule_engine_check',
                result='review_triggered',
                rule_id=review_rule['rule_id'],
                detail=review_rule['description'],
            )

        # --------------------------------------------------
        # Step4：Skill 路由 + 参数构建 + 参数校验
        # --------------------------------------------------
        skill_ids = INTENT_SKILL_MAP.get(intent_category, [])
        selected_skills = []

        for skill_id in skill_ids:
            if skill_id not in SKILL_REGISTRY:
                logger.warning(f'[Node2] 未知 skill_id：{skill_id}，跳过')
                continue

            meta = SKILL_REGISTRY[skill_id]
            params = _build_skill_params(skill_id, entities, [])

            # 有依赖的 Skill 部分入参在 Node3 注入，此处只校验无依赖的 Skill
            # 有依赖的 Skill 在 Node3 注入完整参数后再执行完整校验
            if not meta['depends_on']:
                _validate_params(skill_id, params)

            selected_skills.append({
                'skill_id': skill_id,
                'params': params,
                'depends_on': meta['depends_on'],
            })

        state['working']['route']['selected_skills'] = selected_skills

        duration_ms = int((time.monotonic() - t0) * 1000)
        append_node_trace(state, 'node2_compliance_gate', started_at, 'ok',
                          f'路由到 {len(selected_skills)} 个 Skill，合规通过')

    except BadRequestError:
        raise
    except Exception as e:
        logger.exception(f'[Node2] 执行异常：{e}')
        append_node_trace(state, 'node2_compliance_gate', started_at, 'failed', str(e))
        raise

    return state
