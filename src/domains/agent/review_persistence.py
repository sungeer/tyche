"""
人工审核任务持久化与状态恢复
AgentState 序列化存 DB，审核通过后反序列化并从 Node3 恢复执行。
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.core.db import engine
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import repository
from src.domains.agent.state import append_compliance_event


def _now_utc():
    return datetime.now(timezone.utc)


def _now_utc_str():
    return _now_utc().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


async def save_state_for_review(state, rule_id, assign_to_role, sla_hours):
    """
    将 AgentState 序列化并持久化到 DB，同时创建审核任务记录。
    返回 task_id，用于后续轮询和恢复。
    """
    task_id = uuid.uuid4().hex
    turn_id = state['input']['turn_id']
    user_id = state['input']['user']['user_id']
    sla_deadline = (_now_utc() + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M:%S.000')
    trigger_detail = state['working']['route']['human_review'].get('reason', '')

    # 序列化时排除临时字段（以 _ 开头的字段均为临时字段）
    state_to_save = {k: v for k, v in state.items() if not k.startswith('_')}
    state_json = json.dumps(state_to_save, ensure_ascii=False, default=str)

    def run_sync():
        with engine.begin() as conn:
            repository.insert_review_task(conn, {
                'task_id': task_id,
                'turn_id': turn_id,
                'user_id': user_id,
                'assigned_role': assign_to_role,
                'trigger_rule': rule_id,
                'trigger_detail': trigger_detail,
                'sla_deadline': sla_deadline,
            })
            repository.insert_state_snapshot(conn, task_id, state_json)

    await run_in_threadpool(db_threadpool, run_sync)
    return task_id


async def load_state_snapshot(task_id):
    """从 DB 加载 AgentState 快照，审核通过后恢复执行使用"""
    def run_sync():
        with engine.connect() as conn:
            return repository.get_state_snapshot(conn, task_id)

    row = await run_in_threadpool(db_threadpool, run_sync)
    if not row:
        return None
    return json.loads(row['state_json'])


async def resume_after_review(task_id, reviewer_id, decision, reviewer_note):
    """
    审核人操作后调用此函数。
    decision: 'approved' | 'rejected' | 'escalated'
    返回更新后的 state（仅 approved 时有后续流程）。
    """
    # 延迟导入避免循环依赖
    from src.domains.agent import pipeline

    state = await load_state_snapshot(task_id)
    if not state:
        logger.error(f'[Review] 找不到 task_id={task_id} 的 State 快照')
        return None

    # 将审核决策写入审计轨迹
    append_compliance_event(
        state,
        event_type='human_review_decision',
        result=decision,
        rule_id=task_id,
        detail=f'审核人 {reviewer_id}：{reviewer_note}',
    )

    reviewed_at = _now_utc_str()

    def update_task():
        with engine.begin() as conn:
            repository.update_review_task_status(
                conn, task_id,
                status=decision,
                reviewer_note=reviewer_note,
                reviewed_at=reviewed_at,
            )

    await run_in_threadpool(db_threadpool, update_task)

    if decision == 'approved':
        state['control']['status'] = 'running'
        # 从 Node3 恢复完整执行流程
        state = await pipeline.resume_from_node3(state)

    elif decision == 'rejected':
        state['control']['status'] = 'rejected'
        # 异步写审计日志
        from src.domains.agent.nodes import node5_audit_writer
        import asyncio
        asyncio.create_task(node5_audit_writer.run(state))

    # 'escalated' 时只更新了 DB 状态，通知逻辑由上层调用者处理

    return state
