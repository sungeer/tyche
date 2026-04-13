"""
工作流节点步骤持久化

每个节点执行完成后立即调用 write_step()，将该节点的关键输出实时写入 DB。
进程崩溃时，已写入的步骤不丢失——workflow_step 表即是执行进度的事实来源。

所有公开函数内部捕获异常，不向外传播：
写失败只记录 error 日志，不中断主流程。
"""
import json

from loguru import logger

from src.core.db import engine
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import repository


def _get_latest_trace(state, node_name):
    """从 audit.node_traces 中倒序查找指定节点最近一次的执行轨迹"""
    for trace in reversed(state['audit']['node_traces']):
        if trace['node'] == node_name:
            return trace
    return None


def _extract_step_output(state, node_name):
    """
    从 state 中提取各节点的关键决策输出，结构化存储。
    只记录决策信息，不存储业务数据（客户资产、产品净值等）。
    """
    if node_name == 'node1_intent_parser':
        intent = state['working'].get('intent') or {}
        return {
            'category': intent.get('category'),
            'confidence': intent.get('confidence'),
            'needs_clarification': intent.get('needs_clarification'),
        }

    if node_name == 'node2_compliance_gate':
        route = state['working'].get('route') or {}
        compliance = route.get('compliance') or {}
        hr = route.get('human_review') or {}
        return {
            'compliance_passed': compliance.get('passed'),
            'human_review_required': hr.get('required'),
            'human_review_rule_id': hr.get('rule_id'),
            'skills_selected': [
                s['skill_id'] for s in route.get('selected_skills', [])
            ],
        }

    if node_name == 'node3_skill_executor':
        return {
            'skill_results': [
                {
                    'skill_id': r['skill_id'],
                    'status': r['status'],
                    'duration_ms': r.get('duration_ms', 0),
                    'error_msg': r.get('error_msg') or '',
                }
                for r in state['working'].get('skill_results', [])
            ],
        }

    if node_name == 'node4_response_synthesizer':
        response = state['working'].get('response') or {}
        validation = response.get('validation') or {}
        return {
            'content_filter_passed': validation.get('content_filter_passed'),
            'number_check_passed': validation.get('number_check_passed'),
            'token_usage': response.get('token_usage') or {},
        }

    return {}


async def init_run(state):
    """
    Pipeline 启动时创建 workflow_run 记录。
    在首个节点执行之前调用。
    """
    try:
        def run_sync():
            with engine.begin() as conn:
                repository.insert_workflow_run(
                    conn,
                    turn_id=state['input']['turn_id'],
                    session_id=state['input']['session_id'],
                    user_id=state['input']['user']['user_id'],
                )

        await run_in_threadpool(db_threadpool, run_sync)

    except Exception as e:
        logger.error(f'[StepLog] init_run 失败（不影响主流程）：{e}')


async def write_step(state, node_name):
    """
    节点执行完成后立即调用，将该节点的执行结果持久化。
    依赖各节点在返回前已向 state['audit']['node_traces'] 追加轨迹。
    """
    try:
        trace = _get_latest_trace(state, node_name)
        if not trace:
            logger.warning(f'[StepLog] write_step 未找到节点轨迹：{node_name}，跳过')
            return

        output = _extract_step_output(state, node_name)
        output_json = json.dumps(output, ensure_ascii=False, default=str)

        def run_sync():
            with engine.begin() as conn:
                repository.insert_workflow_step(conn, {
                    'turn_id': state['input']['turn_id'],
                    'node_name': node_name,
                    'status': trace['status'],
                    'output_json': output_json,
                    'error_msg': trace.get('summary', '') if trace['status'] == 'failed' else '',
                    'started_at': trace['started_at'],
                    'ended_at': trace['ended_at'],
                    'duration_ms': trace['duration_ms'],
                })

        await run_in_threadpool(db_threadpool, run_sync)

    except Exception as e:
        logger.error(f'[StepLog] write_step [{node_name}] 失败（不影响主流程）：{e}')


async def finish_run(state):
    """
    Pipeline 结束时更新 workflow_run 的最终状态。
    在 finally 块中调用，确保无论何种结局都能更新。
    """
    try:
        def run_sync():
            with engine.begin() as conn:
                repository.update_workflow_run_status(
                    conn,
                    turn_id=state['input']['turn_id'],
                    status=state['control']['status'],
                )

        await run_in_threadpool(db_threadpool, run_sync)

    except Exception as e:
        logger.error(f'[StepLog] finish_run 失败（不影响主流程）：{e}')
