"""
Node4：LLM 响应合成
将 Skill 结构化数据 + RAG 知识库 chunk + 对话历史组装为 prompt，
调用 LLM 流式生成自然语言答复（SSE）。
流结束后执行数值一致性校验和合规用语过滤。
"""
import json
import re
import time

from loguru import logger

from src.domains.agent import llm
from src.domains.agent.state import (
    append_node_trace,
    append_llm_call,
    append_compliance_event,
    _now_utc,
)

# 合规用语黑名单（正则，可配置扩展）
_FORBIDDEN_PATTERNS = [
    re.compile(r'保证收益'),
    re.compile(r'稳赚'),
    re.compile(r'一定(涨|跌)'),
    re.compile(r'建议(您|你)购买'),
    re.compile(r'推荐投资'),
    re.compile(r'保本'),
]

# 数值提取正则（百分比、金额、整数）
_NUMBER_PATTERN = re.compile(r'\d+\.?\d*%?')

_SYSTEM_PROMPT = '''你是银行投资理财助手，负责将查询结果转述为清晰、准确的自然语言。

严格规则：
1. 只使用 [结构化查询结果] 中提供的数据，不得自行补充或推断数据中没有的内容
2. 禁止使用以下表达：保证收益、稳赚、一定涨/跌、建议购买、推荐投资、保本
3. 所有数值必须与原始数据完全一致，不得四舍五入或变形
4. 若数据为空或查询失败，直接说明未查到，不推断
5. 回答结尾必须注明：本内容由 AI 生成，仅供参考，不构成投资建议

[知识库参考资料]
{knowledge_chunks}

[结构化查询结果]
{skill_results}

[对话历史]
{history}'''


def _format_skill_results(skill_results):
    """将 skill_results 格式化为 prompt 中的结构化文本"""
    if not skill_results:
        return '（无查询结果）'

    parts = []
    for r in skill_results:
        if r['status'] == 'ok' and r['data']:
            parts.append(f'技能: {r["skill_id"]}\n结果: {json.dumps(r["data"], ensure_ascii=False, default=str)}')
        elif r['status'] in ('degraded', 'error', 'timeout'):
            parts.append(f'技能: {r["skill_id"]}\n状态: {r["status"]}（{r.get("error_msg", "执行失败")}）')
    return '\n\n'.join(parts) if parts else '（所有查询均失败）'


def _format_knowledge_chunks(chunks):
    """将 knowledge_chunks 格式化为 prompt 中的参考资料"""
    if not chunks:
        return '（无相关参考资料）'
    parts = [chunk['content'] for chunk in chunks[:3]]
    return '\n---\n'.join(parts)


def _format_history(history):
    """将历史消息格式化为多轮对话文本"""
    if not history:
        return '（无历史）'
    lines = []
    for item in history[-10:]:
        role_label = '用户' if item['role'] == 'user' else '助手'
        lines.append(f'{role_label}：{item["content"]}')
    return '\n'.join(lines)


def _check_compliance(text):
    """
    合规用语检查：扫描文本中的违禁表达。
    返回 (passed: bool, violations: list)。
    """
    violations = []
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(text):
            violations.append(pattern.pattern)
    return len(violations) == 0, violations


def _check_number_consistency(response_text, skill_results):
    """
    数值一致性校验：提取 response 中的数值，与 skill_results 对比。
    目前实现为简单检查，实际需要更精细的字段对应逻辑。
    返回 (passed: bool)。
    """
    # 收集 skill_results 中所有数值字符串
    all_skill_data_text = json.dumps(
        [r.get('data') for r in skill_results if r.get('data')],
        ensure_ascii=False,
        default=str,
    )
    skill_numbers = set(_NUMBER_PATTERN.findall(all_skill_data_text))

    # 提取 response 中的数值
    response_numbers = set(_NUMBER_PATTERN.findall(response_text))

    # 找到 response 中有但 skill_results 中没有的数值（超出 0.01% 阈值忽略浮点误差）
    suspicious = []
    for num in response_numbers:
        # 纯整数（年份等）跳过
        if num.isdigit() and int(num) < 2100:
            continue
        # 数值在 skill 数据中找不到时标记为可疑
        if num not in skill_numbers and len(num) > 2:
            suspicious.append(num)

    return len(suspicious) == 0


def _all_skills_empty(skill_results):
    """判断所有 Skill 是否均返回空数据"""
    for r in skill_results:
        if r['status'] == 'ok' and r['data']:
            return False
    return True


async def run(state, sse_queue=None):
    """Node4 入口：LLM 响应合成（SSE 流式）"""
    started_at = _now_utc()
    t0 = time.monotonic()

    skill_results = state['working']['skill_results']
    knowledge_chunks = state['working']['knowledge_chunks']
    history = state['input']['history']
    message = state['input']['message']

    try:
        # 所有 Skill 均无数据时，直接返回固定文案（FR-044）
        if _all_skills_empty(skill_results):
            fixed_msg = '系统未查询到相关数据，请确认查询条件后重试。'
            state['working']['response'] = {
                'text': fixed_msg,
                'validation': {'number_check_passed': True, 'content_filter_passed': True, 'violations': []},
                'token_usage': {},
            }
            if sse_queue:
                # 推送 SSE 事件 给 event_generator() 消费
                sse_queue.put_nowait({'event': 'token', 'data': {'text': fixed_msg}})
            append_node_trace(state, 'node4_response_synthesizer', started_at, 'ok', '所有 Skill 无数据，返回固定文案')
            return state

        # 组装 prompt
        system_content = _SYSTEM_PROMPT.format(
            knowledge_chunks=_format_knowledge_chunks(knowledge_chunks),
            skill_results=_format_skill_results(skill_results),
            history=_format_history(history),
        )
        messages = [
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': message},
        ]

        # 流式 LLM 调用
        if sse_queue:
            full_text, usage = await llm.stream_chat_completion(messages, sse_queue, timeout=60)
        else:
            # 无 SSE 队列时（如审核恢复场景），使用非流式调用
            resp = await llm.chat_completion(messages, timeout=60)
            full_text = resp['choices'][0]['message']['content']
            usage = resp.get('usage', {
                'prompt_tokens': 0,
                'completion_tokens': 0,
            })

        duration_ms = int((time.monotonic() - t0) * 1000)

        # --------------------------------------------------
        # 后置校验1：合规用语过滤（FR-043）
        # --------------------------------------------------
        compliance_passed, violations = _check_compliance(full_text)
        if not compliance_passed:
            blocked_msg = '当前回答包含不合规表达，已被系统拦截。'
            if sse_queue:
                sse_queue.put_nowait({
                    'event': 'content_blocked',
                    'data': {'type': 'compliance_violation', 'message': blocked_msg},
                })
            append_compliance_event(
                state,
                event_type='content_compliance_check',
                result='blocked',
                rule_id='forbidden_expression',
                detail=f'违规表达：{violations}',
            )
            full_text = blocked_msg

        # --------------------------------------------------
        # 后置校验2：数值一致性（FR-042）
        # --------------------------------------------------
        number_ok = _check_number_consistency(full_text, skill_results)
        if not number_ok:
            warning_msg = '\n\n⚠️ 数据核对发现差异，请以系统数据为准'
            full_text += warning_msg
            if sse_queue:
                sse_queue.put_nowait({
                    'event': 'validation_warning',
                    'data': {'type': 'number_mismatch', 'message': warning_msg.strip()},
                })

        state['working']['response'] = {
            'text': full_text,
            'validation': {
                'number_check_passed': number_ok,
                'content_filter_passed': compliance_passed,
                'violations': violations,
            },
            'token_usage': {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
            },
        }

        append_llm_call(
            state,
            node_name='node4_response_synthesizer',
            model='Qwen3.5-397B-A17B',
            prompt_tokens=usage.get('prompt_tokens', 0),
            completion_tokens=usage.get('completion_tokens', 0),
            duration_ms=duration_ms,
        )
        append_node_trace(
            state, 'node4_response_synthesizer', started_at, 'ok',
            f'响应合成完成，合规={compliance_passed}，数值一致={number_ok}',
        )

    except Exception as e:
        logger.exception(f'[Node4] 执行异常：{e}')
        # 降级：将 skill_results 原始数据返回
        degraded_text = _build_degraded_response(skill_results)
        state['working']['response'] = {
            'text': degraded_text,
            'validation': {'number_check_passed': True, 'content_filter_passed': True, 'violations': []},
            'token_usage': {},
        }
        if sse_queue:
            sse_queue.put_nowait({'event': 'token', 'data': {'text': degraded_text}})
        append_node_trace(state, 'node4_response_synthesizer', started_at, 'failed', str(e))

    return state


def _build_degraded_response(skill_results):
    """Node4 LLM 不可用时的降级响应：直接展示原始查询结果"""
    lines = ['[系统提示] AI 生成服务暂时不可用，以下为原始查询结果：', '']
    for r in skill_results:
        if r['status'] == 'ok' and r['data']:
            lines.append(f'【{r["skill_id"]}】')
            lines.append(json.dumps(r['data'], ensure_ascii=False, indent=2, default=str))
            lines.append('')
    lines.append('（以上数据来自系统实时查询，非 AI 生成）')
    return '\n'.join(lines)
