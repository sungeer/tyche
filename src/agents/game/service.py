from langchain_core.messages import HumanMessage

from src.ai.graph_registry import graph_registry


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


async def chat_stream_and_save(session_id: str, user_input: str):
    input_state = {
        'messages': [HumanMessage(content=user_input)],
        'next': '',
    }
    config = {'configurable': {'thread_id': session_id}}
    graph = graph_registry['game']

    async for token in chat_stream(graph, input_state, config):
        yield token
