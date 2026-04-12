"""
LLM 客户端封装
使用行内私有部署的 Qwen3.5-397B-A17B，通过 httpx 异步调用。
数据库仍用 db_threadpool（驱动稳定性考量），HTTP 用 httpx 原生 async。
"""
import json

import httpx
from loguru import logger

from src.core.config import settings

# 模型名称
_MODEL_NAME = 'Qwen3.5-397B-A17B'


def _build_headers():
    return {
        'Authorization': f'Bearer {settings.llm_api_key}',
        'Content-Type': 'application/json',
    }


# 非流式 LLM 调用
async def chat_completion(messages, json_mode=False, timeout=30):
    payload = {
        'model': _MODEL_NAME,
        'messages': messages,
        'temperature': 0.1,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}

    url = f'{settings.llm_base_url}/v1/chat/completions'

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers=_build_headers(),
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()


# 流式 LLM 调用
async def stream_chat_completion(messages, sse_queue, timeout=60):
    """
    流式 LLM 调用。
    token 逐步推入 sse_queue，返回 (full_text, usage_dict)。
    """
    payload = {
        'model': _MODEL_NAME,
        'messages': messages,
        'temperature': 0.1,
        'stream': True,
    }
    full_text = []
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                f'{settings.llm_base_url}/v1/chat/completions',
                json=payload,
                headers=_build_headers(),
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith('data: '):
                        continue
                    chunk = line[6:]
                    if chunk == '[DONE]':
                        break
                    try:
                        data = json.loads(chunk)
                        # 某些实现在最后 chunk 携带 usage
                        if data.get('usage'):
                            usage['prompt_tokens'] = data['usage'].get('prompt_tokens', 0)
                            usage['completion_tokens'] = data['usage'].get('completion_tokens', 0)
                        content = data['choices'][0]['delta'].get('content', '')
                        if content:
                            full_text.append(content)
                            sse_queue.put_nowait({'event': 'token', 'data': {'text': content}})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

    except Exception as e:
        logger.error(f'[LLM] 流式调用异常：{e}')
        raise

    return ''.join(full_text), usage
