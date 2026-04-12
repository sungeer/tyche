"""
Pipeline 协调器
按顺序调用各节点，传递 AgentState，处理条件分支。
是唯一知道"节点执行顺序"的地方，不含业务逻辑。
"""
import asyncio

from loguru import logger

from src.domains.agent.nodes import (
    node1_intent_parser,
    node2_compliance_gate,
    node3_skill_executor,
    node4_response_synthesizer,
    node5_audit_writer,
)
from src.domains.agent import review_persistence
from src.domains.agent.skill_registry import SKILL_REGISTRY


# Pipeline 主入口 依次执行各节点
async def run(state):
    try:
        # ── Node1：意图识别 ──────────────────────────────────
        state['control']['current_node'] = 'node1'
        state = await node1_intent_parser.run(state)

        # 分支 闲聊或超出范围 直接截断 不写审计
        if _should_short_circuit(state):
            state['control']['status'] = 'short_circuited'  # 意图短路
            state['control']['short_circuit_reason'] = state['working']['intent']['category']  # 短路原因
            _push_short_circuit_response(state)  # 礼貌提示
            return state

        # 分支 意图不明确 返回澄清问题
        if state['working']['intent']['needs_clarification']:
            state['control']['status'] = 'completed'  # 正常完成
            _push_working_response(state)  # 将 working.response.text 推送到 SSE
            return state

        # ── Node2：合规拦截 + Skill 路由 ─────────────────────
        state['control']['current_node'] = 'node2'
        state = await node2_compliance_gate.run(state)

        # 分支：合规拦截 → 返回拒绝原因，写审计
        if not state['working']['route']['compliance']['passed']:
            state['control']['status'] = 'rejected'
            _push_working_response(state)
            asyncio.create_task(node5_audit_writer.run(state))
            return state

        # 分支：触发人工审核 → 持久化 state，返回异步任务 ID
        if state['working']['route']['human_review']['required']:
            state['control']['status'] = 'pending_review'
            review_info = state['working']['route']['human_review']
            task_id = await review_persistence.save_state_for_review(
                state,
                rule_id=review_info['rule_id'],
                assign_to_role=review_info['assign_to_role'],
                sla_hours=review_info['sla_hours'],
            )
            state['review_task_id'] = task_id  # 人工审核任务创建后写入 供 pipeline 后续流转识别
            _push_pending_review(state, task_id, review_info['sla_hours'])
            asyncio.create_task(node5_audit_writer.run(state))
            return state

        # ── Node3：Skill 执行 + RAG 检索 ─────────────────────
        state['control']['current_node'] = 'node3'
        state = await node3_skill_executor.run(state)

        # 分支：写操作 Skill 关键失败 → 整体失败
        if _is_critical_failure(state):
            state['control']['status'] = 'failed'
            _push_error(state, '关键操作执行失败，请稍后重试')
            asyncio.create_task(node5_audit_writer.run(state))
            return state

        # ── Node4：响应合成（LLM，SSE 流式）─────────────────
        state['control']['current_node'] = 'node4'
        state = await node4_response_synthesizer.run(state)

        state['control']['status'] = 'completed'

        # ── Node5：审计写入（异步，不阻塞响应）───────────────
        asyncio.create_task(node5_audit_writer.run(state))

    except Exception as e:
        logger.exception(f'[Pipeline] 未捕获异常：{e}')
        state['control']['status'] = 'failed'
        state['control']['error'] = {
            'node': state['control'].get('current_node', 'unknown'),
            'type': type(e).__name__,
            'message': str(e),
        }
        _push_error(state, '服务暂时不可用，请稍后重试')
        asyncio.create_task(node5_audit_writer.run(state))

    finally:
        # 无论何种结局，都通知 SSE 流结束
        _signal_sse_done(state)

    return state


async def resume_from_node3(state):
    """
    审核人通过后，从 Node3 恢复执行。
    此时 state 已从 DB 加载，Node1/Node2 结果仍在。
    注意：此场景无 SSE 队列，Node4 使用非流式调用。
    """
    try:
        state['control']['current_node'] = 'node3'
        state = await node3_skill_executor.run(state)

        if _is_critical_failure(state):
            state['control']['status'] = 'failed'
            asyncio.create_task(node5_audit_writer.run(state))
            return state

        state['control']['current_node'] = 'node4'
        state = await node4_response_synthesizer.run(state)

        state['control']['status'] = 'completed'
        asyncio.create_task(node5_audit_writer.run(state))

    except Exception as e:
        logger.exception(f'[Pipeline] resume_from_node3 异常：{e}')
        state['control']['status'] = 'failed'
        state['control']['error'] = {
            'node': state['control'].get('current_node', 'unknown'),
            'type': type(e).__name__,
            'message': str(e),
        }
        asyncio.create_task(node5_audit_writer.run(state))

    return state


# ==================== 辅助函数 ====================

# 意图 闲聊或超出范围
def _should_short_circuit(state):
    category = state['working']['intent']['category']
    return category in ('small_talk', 'out_of_scope')


def _is_critical_failure(state):
    """
    存在写操作 Skill 执行失败时，视为关键失败。
    读操作失败（degraded/error）不触发关键失败。
    """
    for result in state['working']['skill_results']:
        skill_meta = SKILL_REGISTRY.get(result['skill_id'], {})
        if skill_meta.get('write_operation') and result['status'] != 'ok':
            return True
    return False


def _get_queue(state):
    return state.get('sse_queue')


# 将 working.response.text 推送到 SSE
def _push_working_response(state):
    queue = _get_queue(state)
    if not queue:
        return
    response = state['working'].get('response')
    if response and response.get('text'):
        queue.put_nowait({'event': 'token', 'data': {'text': response['text']}})


# 闲聊或超出范围的 礼貌提示
def _push_short_circuit_response(state):
    queue = _get_queue(state)
    if not queue:
        return
    category = state['working']['intent']['category']
    if category == 'small_talk':
        text = '您好！我是银行投资理财助手，专注于产品查询、持仓分析、风险评估等专业服务，暂时无法处理闲聊话题，请问有什么理财方面的问题需要帮助？'
    else:
        text = '抱歉，您的请求超出了系统当前的服务范围。如需帮助，请联系相关业务部门。'
    queue.put_nowait({'event': 'token', 'data': {'text': text}})  # 推送 SSE 事件


def _push_pending_review(state, task_id, sla_hours):
    """人工审核等待中的提示"""
    queue = _get_queue(state)
    if not queue:
        return
    text = f'您的操作需要人工审核。\n任务编号：{task_id}\n预计处理时间：{sla_hours} 小时\n\n您可以通过 /agent.task.status?task_id={task_id} 查询处理进度。'
    queue.put_nowait({'event': 'token', 'data': {'text': text}})


def _push_error(state, message):
    """推送错误消息到 SSE"""
    queue = _get_queue(state)
    if not queue:
        return
    queue.put_nowait({'event': 'token', 'data': {'text': message}})


def _signal_sse_done(state):
    """
    发送 SSE done 事件 + None 哨兵，通知 event_generator 结束。
    必须在 finally 块中调用，确保 SSE 流总能正常关闭。
    """
    queue = _get_queue(state)
    if not queue:
        return
    turn_usage = {}
    response = state['working'].get('response')
    if response and response.get('token_usage'):
        turn_usage = response['token_usage']
    queue.put_nowait({
        'event': 'done',
        'data': {
            'turn_id': state['input']['turn_id'],
            'status': state['control']['status'],
            'token_usage': turn_usage,
        },
    })
    queue.put_nowait(None)  # 哨兵值：通知 event_generator 退出循环
