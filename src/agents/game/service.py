from langchain_core.messages import HumanMessage

from src.agents.game.graph_registry import graph_registry


async def _chat_stream(graph, input_state: dict, config: dict):
    async for event in graph.astream_events(input_state, config, version='v2'):
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


async def chat_stream(session_id: str, user_input: str):
    input_state = {
        'messages': [HumanMessage(content=user_input)],
        'next': '',
    }
    config = {
        'configurable': {
            'thread_id': session_id
        }
    }
    graph = graph_registry['game']

    async for token in _chat_stream(graph, input_state, config):
        yield token
