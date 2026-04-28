from loguru import logger
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.ai.core.graph_registry import graph_registry
from src.core.db import db
from src.domains.agent import repository

_role_map = {
    'user': HumanMessage,
    'assistant': AIMessage,
    'system': SystemMessage,
}


# 指定话题下的 历史消息
async def load_history(session_id: str) -> list:
    async with db.connect() as conn:
        conversation_id = await repository.get_conversation_id(conn, session_id)
        if not conversation_id:
            return []
        rows = await repository.get_messages(conn, conversation_id)

    messages = []
    for r in rows:
        role = r['role']
        if role not in _role_map:
            continue
        message_cls = _role_map[role]
        messages.append(message_cls(content=r['content']))
    return messages


async def save_turn_messages(session_id: str, user_id: int, user_message: str, assistant_response: str) -> None:
    async with db.begin() as conn:
        conversation_id = await repository.get_conversation_id(conn, session_id)
        if not conversation_id:
            # 创建 新话题
            conversation_id = await repository.create_conversation(conn, user_id, session_id)
        # 创建 问答
        await repository.insert_message(conn, conversation_id, 'user', user_message)
        await repository.insert_message(conn, conversation_id, 'assistant', assistant_response)
    return None


async def chat_stream(graph, input_state: dict, config: dict):
    async for event in graph.astream_events(input_state, config, version='v2'):
        if event['event'] != 'on_chat_model_stream':
            continue
        # supervisor 输出的是结构化路由 JSON，不是回复内容
        if event.get('metadata', {}).get('langgraph_node') == 'supervisor':
            continue
        chunk = event['data']['chunk']
        if chunk.content:
            yield chunk.content


async def chat_stream_and_save(session_id: str, user_input: str, user_id: int):
    history = await load_history(session_id)
    full_text = ''

    input_state = {
        'messages': history + [HumanMessage(content=user_input)],
        'next': '',
    }
    config = {'configurable': {'thread_id': session_id}}
    graph = graph_registry['game']

    async for token in chat_stream(graph, input_state, config):
        full_text += token
        yield token

    try:
        await save_turn_messages(
            session_id=session_id,
            user_id=user_id,
            user_message=user_input,
            assistant_response=full_text,
        )
    except Exception as e:
        logger.error(f'[chat] 消息保存失败：{e}')
