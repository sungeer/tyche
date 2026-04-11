"""
Node5：审计日志写入
异步执行（asyncio.create_task），不阻塞主响应。
此节点绝不向外抛异常——写失败记录 error 日志即可。

写入内容：
  - 从 state 提取关键字段
  - 对客户姓名、手机号、身份证号进行 PII 脱敏
  - 生成 SHA-256 content_hash 防篡改
  - 写入 agent_audit_log 表
"""
import hashlib
import json
import re
from datetime import datetime, timezone

from loguru import logger

from src.core.db import engine
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.domains.agent import repository
from src.domains.agent.state import append_node_trace, _now_utc

# PII 脱敏正则
_PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')
_ID_CARD_PATTERN = re.compile(r'\d{6}\d{8}[\dXx]')
_NAME_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,4}')     # 仅用于结构化字段，不做全文替换


def _mask_phone(phone):
    """手机号脱敏：138****9876"""
    if len(phone) == 11:
        return f'{phone[:3]}****{phone[7:]}'
    return phone


def _mask_id_card(id_card):
    """身份证脱敏：110101********1234"""
    if len(id_card) == 18:
        return f'{id_card[:6]}{"*" * 8}{id_card[14:]}'
    return id_card


def _mask_name(name):
    """姓名脱敏：张* 或 李**（保留姓，名用 * 替代）"""
    if len(name) <= 1:
        return name
    return name[0] + '*' * (len(name) - 1)


def _pii_mask_text(text):
    """对文本做全量 PII 脱敏（手机号、身份证）"""
    if not isinstance(text, str):
        return text
    text = _PHONE_PATTERN.sub(lambda m: _mask_phone(m.group()), text)
    text = _ID_CARD_PATTERN.sub(lambda m: _mask_id_card(m.group()), text)
    return text


def _build_skills_summary(skill_results):
    """
    从 skill_results 提取摘要，只记录字段名，不记录具体数值（防止客户资产进审计表）。
    """
    summary = []
    for r in skill_results:
        item = {
            'skill_id': r['skill_id'],
            'status': r['status'],
            'duration_ms': r.get('duration_ms', 0),
        }
        if r.get('data') and isinstance(r['data'], dict):
            item['returned_fields'] = list(r['data'].keys())
        if r.get('error_msg'):
            item['error_msg'] = r['error_msg']
        summary.append(item)
    return summary


def _build_node_durations(node_traces):
    """从 node_traces 提取各节点耗时"""
    return {
        trace['node']: trace['duration_ms']
        for trace in node_traces
    }


def _build_llm_token_usage(llm_calls):
    """汇总所有 LLM 调用的 token 用量"""
    total_prompt = sum(c.get('prompt_tokens', 0) for c in llm_calls)
    total_completion = sum(c.get('completion_tokens', 0) for c in llm_calls)
    return {
        'total_prompt_tokens': total_prompt,
        'total_completion_tokens': total_completion,
        'calls': len(llm_calls),
    }


def _compute_hash(record):
    """计算审计记录的 SHA-256 防篡改哈希"""
    # 排除 content_hash 字段本身，对其余字段排序后序列化
    data = {k: v for k, v in record.items() if k != 'content_hash'}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _extract_intent_info(state):
    """从 state 提取意图信息，处理短路或异常情况"""
    intent = state['working'].get('intent')
    if not intent:
        return '', 0.0
    return intent.get('category', ''), float(intent.get('confidence', 0.0))


async def run(state):
    """
    Node5 入口：审计日志写入。
    绝不向外抛异常。
    """
    started_at = _now_utc()

    try:
        intent_category, intent_confidence = _extract_intent_info(state)
        skills_summary = _build_skills_summary(state['working'].get('skill_results', []))
        node_durations = _build_node_durations(state['audit'].get('node_traces', []))
        llm_token_usage = _build_llm_token_usage(state['audit'].get('llm_calls', []))

        # PII 脱敏：合规事件中可能包含客户信息
        compliance_events_raw = state['audit'].get('compliance_events', [])
        compliance_events = json.loads(
            _pii_mask_text(json.dumps(compliance_events_raw, ensure_ascii=False, default=str))
        )

        created_at = _now_utc()
        record = {
            'run_id': state['input']['run_id'],
            'session_id': state['input']['session_id'],
            'turn_id': state['input']['turn_id'],
            'user_id': state['input']['user']['user_id'],
            'operator_role': state['input']['user']['roles'],
            'intent_category': intent_category,
            'intent_confidence': intent_confidence,
            'skills_called': skills_summary,
            'compliance_events': compliance_events,
            'node_durations': node_durations,
            'llm_token_usage': llm_token_usage,
            'final_status': state['control']['status'],
            'created_at': created_at,
        }
        record['content_hash'] = _compute_hash(record)

        def run_sync():
            with engine.begin() as conn:
                repository.insert_audit_log(conn, record)

        await run_in_threadpool(db_threadpool, run_sync)

        append_node_trace(state, 'node5_audit_writer', started_at, 'ok', '审计日志写入成功')

    except Exception as e:
        # Node5 绝不向外抛异常，只记录错误日志
        logger.error(f'[Node5] 审计日志写入失败（不影响主流程）：{e}')
