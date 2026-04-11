"""
Agent 业务编排层
负责会话生命周期管理、审核任务分发等跨层协调逻辑。
"""
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from loguru import logger

from src.core.db import engine
from src.core.exceptions import BadRequestError, ForbiddenError
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import repository, review_persistence

# 会话空闲超时：4 小时
_SESSION_IDLE_TIMEOUT_HOURS = 4

# 每会话最多保留的消息条数（20 轮 × 2 = 40 条）
_MAX_MESSAGES = 40

# 具备审核权限的角色
_REVIEW_ROLES = ('COMPLIANCE', 'RISK_OFFICER', 'ADMIN')



def _now_utc():
    return datetime.now(timezone.utc)


def _is_session_expired(session):
    """判断会话是否已超时（空闲 > 4 小时）"""
    last_active = session.get('last_active_at')
    if not last_active:
        return True

    if isinstance(last_active, str):
        # 字符串格式（某些驱动返回字符串）
        try:
            last_active = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except ValueError:
            last_active = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    elif isinstance(last_active, datetime):
        # SQLAlchemy 通常返回无时区的 datetime，补充 UTC
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)

    delta = _now_utc() - last_active
    return delta > timedelta(hours=_SESSION_IDLE_TIMEOUT_HOURS)


async def load_or_create_session(user_id, session_id):
    """
    加载现有会话，或在以下情况创建新会话：
      - session_id 为空
      - session_id 对应的会话不存在
      - 会话已超时（空闲 > 4 小时）
      - 会话已关闭
    返回 (session_dict, history_list)。
    """
    new_session_id = session_id

    def run_sync():
        with engine.begin() as conn:
            session = None

            if new_session_id:
                session = repository.get_session_by_id(conn, new_session_id)

            # 检查会话有效性
            need_new = (
                not session
                or session.get('status') != 'active'
                or _is_session_expired(session)
            )

            if need_new:
                # 关闭旧会话
                if session and session.get('status') == 'active':
                    repository.close_session(conn, session['session_id'])

                # 创建新会话
                created_id = uuid.uuid4().hex
                repository.create_session(conn, created_id, user_id)
                session = repository.get_session_by_id(conn, created_id)
                history = []
            else:
                # 加载历史消息
                messages = repository.get_messages_by_session(
                    conn, session['session_id'], limit=_MAX_MESSAGES
                )
                history = [
                    {'role': m['role'], 'content': m['content']}
                    for m in messages
                ]

            return session, history

    return await run_in_threadpool(db_threadpool, run_sync)


async def save_turn_messages(session_id, turn_id, user_message, assistant_response):
    """
    保存本轮的用户消息和助手回复到 agent_message 表，
    同时更新会话活跃时间和轮次数。
    user_message 为 None 时（如审核恢复场景）跳过用户消息插入。
    """
    def run_sync():
        with engine.begin() as conn:
            if user_message is not None:
                repository.insert_message(conn, session_id, turn_id, 'user', user_message)
            if assistant_response:
                repository.insert_message(conn, session_id, turn_id, 'assistant', assistant_response)
            repository.update_session_active(conn, session_id)

    await run_in_threadpool(db_threadpool, run_sync)


async def clear_session(user_id, session_id):
    """用户主动清除会话上下文，关闭当前会话
    会话不存在或不属于该用户时抛出 BadRequestError。
    """
    def run_sync():
        with engine.begin() as conn:
            session = repository.get_session_by_id(conn, session_id)
            if not session or session['user_id'] != user_id:
                return False
            repository.close_session(conn, session_id)
            return True

    success = await run_in_threadpool(db_threadpool, run_sync)
    if not success:
        raise BadRequestError('会话不存在或无权操作')


async def get_task_status(task_id):
    """
    查询审核任务状态。
    若任务已完成（approved），同时返回 assistant 消息（从 agent_message 查询）。
    任务不存在时抛出 BadRequestError。
    """
    def run_sync():
        with engine.connect() as conn:
            task = repository.get_review_task(conn, task_id)
            if not task:
                return None

            result = {
                'task_id': task['task_id'],
                'status': task['status'],
                'trigger_rule': task['trigger_rule'],
                'trigger_detail': task['trigger_detail'],
                'assigned_role': task['assigned_role'],
                'sla_deadline': str(task['sla_deadline']),
                'reviewed_at': str(task['reviewed_at']) if task.get('reviewed_at') else None,
                'reviewer_note': task['reviewer_note'],
                'response': None,
            }

            # 若已通过审核，从 agent_message 查询助手回复
            if task['status'] == 'approved':
                msg = repository.get_assistant_message_by_turn_id(conn, task['turn_id'])
                if msg:
                    result['response'] = msg['content']

            return result

    result = await run_in_threadpool(db_threadpool, run_sync)
    if not result:
        raise BadRequestError(f'任务 {task_id} 不存在')
    return result


async def get_review_list(user_roles, limit=50):
    """查询当前用户可审核的任务列表
    从 user_roles 中识别审核角色，无合法审核角色时抛出 ForbiddenError。
    """
    matched = [r for r in user_roles if r in _REVIEW_ROLES]
    if not matched:
        raise ForbiddenError('当前角色无权查看审核任务')
    role, *_ = matched

    def run_sync():
        with engine.connect() as conn:
            return repository.get_pending_review_tasks_by_role(conn, role, limit)

    return await run_in_threadpool(db_threadpool, run_sync)


async def process_review_decision(task_id, reviewer_id, decision, reviewer_note):
    """
    处理审核人操作（通过/驳回/转审）。
    decision: 'approved' | 'rejected' | 'escalated'
    任务快照不存在时抛出 BadRequestError。
    """
    state = await review_persistence.resume_after_review(
        task_id, reviewer_id, decision, reviewer_note
    )
    if not state:
        raise BadRequestError(f'任务 {task_id} 不存在或状态快照丢失')

    # 如果审核通过且有助手回复，保存消息
    if decision == 'approved':
        response = state['working'].get('response')
        if response and response.get('text'):
            await save_turn_messages(
                session_id=state['input']['session_id'],
                turn_id=state['input']['turn_id'],
                user_message=None,
                assistant_response=response['text'],
            )

    return state


def _p95(values):
    """计算列表的 P95 值"""
    if not values:
        return 0
    idx = int(len(values) * 0.95)
    return sorted(values)[min(idx, len(values) - 1)]


async def get_metrics(since_hours=24):
    """
    计算近 N 小时的系统指标：
      - 各节点 P95 耗时（ms）
      - 请求总量与错误率
      - Skill 调用分布
      - 意图分布
    """
    since_dt = (_now_utc() - timedelta(hours=since_hours)).strftime('%Y-%m-%d %H:%M:%S')

    def run_sync():
        with engine.connect() as conn:
            return repository.get_recent_audit_logs_for_metrics(conn, since_dt)

    logs = await run_in_threadpool(db_threadpool, run_sync)

    total = len(logs)
    if not total:
        return {
            'period_hours': since_hours,
            'total_requests': 0,
            'error_rate': 0.0,
            'node_p95_ms': {},
            'skill_call_distribution': {},
            'intent_distribution': {},
        }

    # 错误率
    error_count = sum(1 for log in logs if log['final_status'] in ('failed', 'error'))

    # 各节点耗时收集
    node_durations_map = defaultdict(list)
    for log in logs:
        durations = json.loads(log['node_durations'] or '{}')
        for node, ms in durations.items():
            if isinstance(ms, (int, float)):
                node_durations_map[node].append(ms)

    # Skill 调用分布
    skill_counts = defaultdict(int)
    for log in logs:
        for skill in json.loads(log['skills_called'] or '[]'):
            if skill.get('skill_id'):
                skill_counts[skill['skill_id']] += 1

    # 意图分布
    intent_counts = defaultdict(int)
    for log in logs:
        if log.get('intent_category'):
            intent_counts[log['intent_category']] += 1

    return {
        'period_hours': since_hours,
        'total_requests': total,
        'error_rate': round(error_count / total, 4),
        'node_p95_ms': {node: _p95(vals) for node, vals in node_durations_map.items()},
        'skill_call_distribution': dict(skill_counts),
        'intent_distribution': dict(intent_counts),
    }
