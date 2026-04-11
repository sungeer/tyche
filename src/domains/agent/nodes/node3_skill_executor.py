"""
Node3：Skill 执行 + RAG 检索
按拓扑排序将 Skill 分组，每组内部并发执行。
RAG 检索与第一轮 Skill 并发进行。
"""
import asyncio
import time

from loguru import logger

from src.core.db import engine
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import rag
from src.domains.agent.skill_registry import SKILL_REGISTRY
from src.domains.agent.state import append_node_trace, _now_utc

# Skill 实现函数映射（模块级空 dict，首次调用时原地填充，避免 global）
_SKILL_FUNCTIONS = {}


def _get_skill_functions():
    """延迟加载 Skill 函数映射，避免循环导入"""
    if not _SKILL_FUNCTIONS:
        from src.domains.agent.skills import product, portfolio, risk, redemption, audit
        _SKILL_FUNCTIONS.update({
            'query_product_detail':         product.query_product_detail,
            'query_product_nav_history':    product.query_product_nav_history,
            'query_product_risk_metrics':   product.query_product_risk_metrics,
            'query_customer_portfolio':     portfolio.query_customer_portfolio,
            'query_portfolio_risk_summary': portfolio.query_portfolio_risk_summary,
            'run_stress_test':              risk.run_stress_test,
            'query_redemption_quota':       redemption.query_redemption_quota,
            'initiate_redemption':          redemption.initiate_redemption,
            'query_audit_logs':             audit.query_audit_logs,
        })
    return _SKILL_FUNCTIONS


def _topo_sort(selected_skills):
    """
    拓扑排序：将 selected_skills 分为多轮（Round）。
    同一轮内的 Skill 可并发执行，后轮依赖前轮结果。
    返回 [[skill_call, ...], [skill_call, ...], ...]。
    """
    rounds = []
    remaining = list(selected_skills)
    completed = set()

    while remaining:
        # 本轮：所有依赖均已完成的 Skill
        current_round = [
            s for s in remaining
            if all(dep in completed for dep in s.get('depends_on', []))
        ]
        if not current_round:
            # 出现循环依赖或无法满足的依赖，将剩余全部放入一轮（兜底）
            logger.warning(f'[Node3] 依赖无法满足，剩余 Skill 强制执行：{[s["skill_id"] for s in remaining]}')
            rounds.append(remaining)
            break
        rounds.append(current_round)
        for s in current_round:
            completed.add(s['skill_id'])
            remaining.remove(s)

    return rounds


def _is_async_skill(skill_fn):
    """判断 Skill 实现函数是否为 async（用于决定调用方式）"""
    return asyncio.iscoroutinefunction(skill_fn)


async def _execute_one_skill(skill_call, state, prev_results):
    """
    执行单个 Skill，包含超时控制和降级处理。
    prev_results 用于注入依赖数据（如 portfolio_snapshot）。
    """
    skill_id = skill_call['skill_id']
    params = dict(skill_call['params'])
    meta = SKILL_REGISTRY[skill_id]
    started_at = time.monotonic()

    # 写操作生成幂等键
    if meta['write_operation']:
        params['idempotency_key'] = f'{state["input"]["turn_id"]}:{skill_id}'

    # 依赖注入：将前置 Skill 结果注入 params
    if meta['depends_on'] and prev_results:
        for dep_id in meta['depends_on']:
            for prev in prev_results:
                if prev['skill_id'] == dep_id and prev['status'] == 'ok':
                    # run_stress_test 特殊处理：注入 portfolio_snapshot
                    if skill_id == 'run_stress_test' and dep_id == 'query_customer_portfolio':
                        params['portfolio_snapshot'] = prev['data']

    # 有依赖的 Skill 在 Node2 跳过了完整校验，此处补充校验
    if meta['depends_on']:
        import jsonschema
        from src.core.exceptions import BadRequestError
        try:
            jsonschema.validate(instance=params, schema=meta['params_schema'])
        except jsonschema.ValidationError as e:
            return {
                'skill_id': skill_id,
                'status': 'error',
                'data': None,
                'error_msg': f'参数校验失败（依赖注入后）：{e.message}',
                'duration_ms': 0,
                'idempotency_key': params.get('idempotency_key'),
            }

    skill_fn = _get_skill_functions().get(skill_id)
    if skill_fn is None:
        return {
            'skill_id': skill_id,
            'status': 'error',
            'data': None,
            'error_msg': f'Skill [{skill_id}] 未找到实现函数',
            'duration_ms': 0,
            'idempotency_key': params.get('idempotency_key'),
        }

    try:
        timeout_s = meta['timeout_ms'] / 1000

        if _is_async_skill(skill_fn):
            # async Skill（如 run_stress_test）：直接 await，httpx 原生异步
            result_data = await asyncio.wait_for(
                skill_fn(params, None),
                timeout=timeout_s,
            )
        else:
            # 同步 DB Skill：offload 到 db_threadpool（同步 MySQL 驱动）
            # 写操作使用 begin()（自动提交），读操作使用 connect()
            def run_db():
                ctx = engine.begin() if meta['write_operation'] else engine.connect()
                with ctx as conn:
                    return skill_fn(params, conn)
            result_data = await asyncio.wait_for(
                run_in_threadpool(db_threadpool, run_db),
                timeout=timeout_s,
            )

        return {
            'skill_id': skill_id,
            'status': 'ok',
            'data': result_data,
            'error_msg': None,
            'duration_ms': int((time.monotonic() - started_at) * 1000),
            'idempotency_key': params.get('idempotency_key'),
        }

    except asyncio.TimeoutError:
        status = 'degraded' if meta['allows_degradation'] else 'error'
        return {
            'skill_id': skill_id,
            'status': status,
            'data': None,
            'error_msg': f'Skill [{skill_id}] 超时（>{meta["timeout_ms"]}ms）',
            'duration_ms': meta['timeout_ms'],
            'idempotency_key': params.get('idempotency_key'),
        }

    except Exception as e:
        return {
            'skill_id': skill_id,
            'status': 'error',
            'data': None,
            'error_msg': str(e),
            'duration_ms': int((time.monotonic() - started_at) * 1000),
            'idempotency_key': params.get('idempotency_key'),
        }


async def run(state):
    """Node3 入口：Skill 执行 + RAG 检索"""
    started_at = _now_utc()

    selected_skills = state['working']['route']['selected_skills']
    all_results = []

    try:
        rounds = _topo_sort(selected_skills)

        for round_idx, round_skills in enumerate(rounds):
            # 第一轮与 RAG 检索并发执行
            if round_idx == 0:
                skill_coros = [
                    _execute_one_skill(s, state, all_results) for s in round_skills
                ]
                rag_coro = rag.retrieve(state)

                gathered = await asyncio.gather(
                    *skill_coros,
                    rag_coro,
                    return_exceptions=True,
                )

                for i, result in enumerate(gathered[:-1]):
                    if isinstance(result, Exception):
                        skill_id = round_skills[i]['skill_id']
                        meta = SKILL_REGISTRY.get(skill_id, {})
                        all_results.append({
                            'skill_id': skill_id,
                            'status': 'error',
                            'data': None,
                            'error_msg': str(result),
                            'duration_ms': 0,
                            'idempotency_key': None,
                        })
                    else:
                        all_results.append(result)

                # RAG 结果（最后一个）
                rag_result = gathered[-1]
                if isinstance(rag_result, Exception):
                    logger.warning(f'[Node3] RAG 检索异常（已降级）：{rag_result}')
                    state['working']['knowledge_chunks'] = []
                else:
                    state['working']['knowledge_chunks'] = rag_result

            else:
                # 后续轮次：只执行 Skill，串行等待
                skill_coros = [
                    _execute_one_skill(s, state, all_results) for s in round_skills
                ]
                results = await asyncio.gather(*skill_coros, return_exceptions=True)

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        skill_id = round_skills[i]['skill_id']
                        all_results.append({
                            'skill_id': skill_id,
                            'status': 'error',
                            'data': None,
                            'error_msg': str(result),
                            'duration_ms': 0,
                            'idempotency_key': None,
                        })
                    else:
                        all_results.append(result)

        state['working']['skill_results'] = all_results

        ok_count = sum(1 for r in all_results if r['status'] == 'ok')
        append_node_trace(
            state, 'node3_skill_executor', started_at, 'ok',
            f'执行 {len(all_results)} 个 Skill，成功 {ok_count} 个；RAG chunks={len(state["working"]["knowledge_chunks"])}',
        )

    except Exception as e:
        logger.exception(f'[Node3] 执行异常：{e}')
        append_node_trace(state, 'node3_skill_executor', started_at, 'failed', str(e))
        raise

    return state
