import uuid
from datetime import datetime, timezone

from src.core.context import run_id_var


def _now_utc():
    return datetime.now(timezone.utc).isoformat()


def make_initial_state(message, user, session, history):
    """
    构建 AgentState 初始值。
    input 域在此一次性填充，其余域均为空/默认值。
    节点函数不得修改 input 域。
    """
    return {

        # ======================================================
        # 输入域（只读，Pipeline 入口写入，节点不得修改）
        # ======================================================
        'input': {
            'session_id': session['session_id'],
            'turn_id': uuid.uuid4().hex,
            'run_id': run_id_var.get('-'),
            'user': {
                'user_id': user.user_id,
                'username': user.username,
                'roles': user.roles,
                # JWT 中暂无以下字段，默认空字符串
                'risk_clearance': getattr(user, 'risk_clearance', ''),
                'department': getattr(user, 'department', ''),
            },
            'message': message,
            'history': history,
            'received_at': _now_utc(),
        },

        # ======================================================
        # 工作域（各节点依次填充）
        # ======================================================
        'working': {
            'intent': None,
            'route': None,
            'skill_results': [],
            'knowledge_chunks': [],
            'response': None,
        },

        # ======================================================
        # 审计域（只追加，不修改已有条目）
        # ======================================================
        'audit': {
            'node_traces': [],
            'compliance_events': [],
            'llm_calls': [],
        },

        # ======================================================
        # 控制域（流程控制信号）
        # ======================================================
        'control': {
            'current_node': None,
            'status': 'running',
            'short_circuit_reason': None,
            'error': None,
        },
    }


def append_node_trace(state, node_name, started_at, status, summary):
    """追加节点执行轨迹到 audit.node_traces"""
    ended_at = _now_utc()
    duration_ms = _calc_duration_ms(started_at, ended_at)
    state['audit']['node_traces'].append({
        'node': node_name,
        'started_at': started_at,
        'ended_at': ended_at,
        'duration_ms': duration_ms,
        'status': status,
        'summary': summary,
    })


def append_compliance_event(state, event_type, result, rule_id, detail):
    """追加合规事件到 audit.compliance_events"""
    state['audit']['compliance_events'].append({
        'event_type': event_type,
        'result': result,
        'rule_id': rule_id,
        'detail': detail,
        'at': _now_utc(),
    })


def append_llm_call(state, node_name, model, prompt_tokens, completion_tokens, duration_ms):
    """追加 LLM 调用记录到 audit.llm_calls"""
    state['audit']['llm_calls'].append({
        'node': node_name,
        'model': model,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'duration_ms': duration_ms,
        'at': _now_utc(),
    })


def _calc_duration_ms(started_at_iso, ended_at_iso):
    """计算两个 ISO8601 时间戳之间的毫秒差"""
    try:
        start = datetime.fromisoformat(started_at_iso)
        end = datetime.fromisoformat(ended_at_iso)
        return int((end - start).total_seconds() * 1000)
    except Exception:
        return 0
