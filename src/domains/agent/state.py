import uuid
from datetime import datetime, timezone

from src.core.context import run_id_var


def now_utc():
    return datetime.now(timezone.utc).isoformat()


# 构建 AgentState 初始值
def make_initial_state(message, user, session, history):
    return {

        # 输入域 只读 pipeline 入口写入 节点不得修改
        'input': {
            'session_id': session['session_id'],  # 当前会话 ID
            'turn_id': uuid.uuid4().hex,  # 本轮对话唯一 ID 用于关联消息和审计
            'run_id': run_id_var.get('-'),  # 请求级追踪 ID 用于日志追踪
            'user': {
                'user_id': user.user_id,  # 当前登录用户 ID
                'username': user.username,
                'roles': user.roles,  # 用户角色 列表 Node2 权限检查的依据
                'risk_clearance': getattr(user, 'risk_clearance', ''),  # 风险许可等级 JWT 暂无
                'department': getattr(user, 'department', ''),  # 所属部门 JWT 暂无
            },
            'message': message,  # 用户本轮输入的原始文本
            'history': history,  # 会话历史消息 [{'role': 'user'/'assistant', 'content': '...'}]
            'received_at': now_utc(),  # 请求接收时间 用于审计和耗时计算
        },

        # 工作域 各节点依次填充
        'working': {
            'intent': None,  # 意图识别的 LLM 结构化输出
            'route': None,  # 合规检查结果 与 Skill 路由决策
            'skill_results': [],  # 所有 Skill 执行结果的列表
            'knowledge_chunks': [],  # RAG 检索返回的知识库片段列表
            'response': None,  # 最终返回给用户的完整响应
        },

        # 审计域 只追加，不修改已有条目
        'audit': {
            'node_traces': [],  # 记录每个节点的执行轨迹
            'compliance_events': [],  # 合规检查触发的事件列表
            'llm_calls': [],  # 每次 LLM 调用的记录
        },

        # 控制域 流程控制信号
        'control': {
            'current_node': None,  # 当前正在执行的节点名 用于异常定位
            'status': 'running',  # 流程最终状态
            'short_circuit_reason': None,  # 短路原因
            'error': None,  # 未捕获异常时写入
            'review_task_id': None,  # 触发人工审核后写入审核任务 ID；未触发时为 None
        },
    }


# 追加节点 执行轨迹 到 audit.node_traces
def append_node_trace(state, node_name, started_at, status, summary):
    ended_at = now_utc()
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
        'at': now_utc(),
    })


# 追加 LLM 调用记录 到 audit.llm_calls
def append_llm_call(state, node_name, model, prompt_tokens, completion_tokens, duration_ms):
    state['audit']['llm_calls'].append({
        'node': node_name,
        'model': model,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'duration_ms': duration_ms,
        'at': now_utc(),
    })


def _calc_duration_ms(started_at_iso, ended_at_iso):
    """计算两个 ISO8601 时间戳之间的毫秒差"""
    try:
        start = datetime.fromisoformat(started_at_iso)
        end = datetime.fromisoformat(ended_at_iso)
        return int((end - start).total_seconds() * 1000)
    except Exception:
        return 0
