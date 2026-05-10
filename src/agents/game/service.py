from langchain_core.messages import HumanMessage, AIMessage

from src.core.db_registry import db
from src.agents.game import repository
from src.agents.game.graph_registry import graph_registry


async def _chat_stream(graph, input_state: dict):
    async for event in graph.astream_events(input_state, {}, version='v2'):
        # 非文字 事件
        if event['event'] != 'on_chat_model_stream':
            continue
        # supervisor 节点的调度内容
        if event.get('metadata', {}).get('langgraph_node') == 'supervisor':
            continue
        # AI 回复的文字
        chunk = event['data']['chunk']
        if chunk.content:
            yield chunk.content


async def _get_or_create_conversation(session_id: str, user_id: int) -> int:
    async with db.connect() as conn:
        conversation_id = await repository.get_conversation_id(conn, session_id)
    if conversation_id is None:
        async with db.begin() as conn:
            conversation_id = await repository.create_conversation(conn, user_id, session_id)
    return conversation_id


async def chat_stream(session_id: str, user_id: int, user_input: str):
    conversation_id = await _get_or_create_conversation(session_id, user_id)

    async with db.connect() as conn:
        raw_messages = await repository.get_messages(conn, conversation_id)

    history = []
    for msg in raw_messages:
        if msg['role'] == 'user':
            history.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            history.append(AIMessage(content=msg['content']))

    input_state = {
        'messages': history + [HumanMessage(content=user_input)],
        'next': '',
    }

    graph = graph_registry['game']
    tokens = []

    async for token in _chat_stream(graph, input_state):
        tokens.append(token)
        yield token

    async with db.begin() as conn:
        await repository.insert_message(conn, conversation_id, 'user', user_input)
        await repository.insert_message(conn, conversation_id, 'assistant', ''.join(tokens))
