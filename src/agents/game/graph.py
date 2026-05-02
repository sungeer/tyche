from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode

from src.core.llm_registry import llm_registry
from src.agents.game import tools, prompts
from src.agents.game.schema import GameState, RouterOutput

# ToolNode 实际 执行工具
tool_node_a = ToolNode([tools.search_web, tools.calculate])
tool_node_b = ToolNode([tools.calculate, tools.query_database])
tool_node_c = ToolNode([tools.search_web, tools.query_database])


# 条件路由
def route_supervisor(state: GameState) -> str:
    return state['next']


def build_game_graph(checkpointer):
    llm = llm_registry['common']

    _supervisor_llm = llm.with_structured_output(RouterOutput)  # 绑定 结构化 输出

    _llm_a = llm.bind_tools([tools.search_web, tools.calculate])
    _llm_b = llm.bind_tools([tools.calculate, tools.query_database])
    _llm_c = llm.bind_tools([tools.search_web, tools.query_database])

    # 主 Agent
    async def supervisor_node(state: GameState) -> dict:
        recent_message_limit = 6  # 最近的 3 轮问答
        recent_messages = state['messages'][-recent_message_limit:]

        routing = await _supervisor_llm.ainvoke([
            SystemMessage(content=prompts.supervisor_agent_prompt),
            *recent_messages,
        ])
        return {'next': routing.next}

    # 子 Agent
    async def agent_a_node(state: GameState):
        messages = [SystemMessage(content=prompts.agent_a_prompt)] + state['messages']
        response = await _llm_a.ainvoke(messages)
        return {'messages': [response]}

    async def agent_b_node(state: GameState):
        messages = [SystemMessage(content=prompts.agent_b_prompt)] + state['messages']
        response = await _llm_b.ainvoke(messages)
        return {'messages': [response]}

    async def agent_c_node(state: GameState):
        messages = [SystemMessage(content=prompts.agent_c_prompt)] + state['messages']
        response = await _llm_c.ainvoke(messages)
        return {'messages': [response]}

    def route_agent_a(state: GameState) -> str:
        last = state['messages'][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return 'tool_node_a'
        return END  # 确保了 agent 执行完毕后 图会正常结束

    def route_agent_b(state: GameState) -> str:
        last = state['messages'][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return 'tool_node_b'
        return END

    def route_agent_c(state: GameState) -> str:
        last = state['messages'][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return 'tool_node_c'
        return END

    builder = StateGraph(GameState)  # type: ignore[arg-type]

    # 注册节点
    builder.add_node('supervisor', supervisor_node)  # type: ignore[arg-type]
    builder.add_node('agent_a', agent_a_node)  # type: ignore[arg-type]
    builder.add_node('agent_b', agent_b_node)  # type: ignore[arg-type]
    builder.add_node('agent_c', agent_c_node)  # type: ignore[arg-type]
    builder.add_node('tool_node_a', tool_node_a)
    builder.add_node('tool_node_b', tool_node_b)
    builder.add_node('tool_node_c', tool_node_c)

    # 设置入口
    builder.add_edge(START, 'supervisor')

    # 添加 条件路由
    builder.add_conditional_edges(
        'supervisor',
        route_supervisor,  # 读取 state 值
        {
            'agent_a': 'agent_a',
            'agent_b': 'agent_b',
            'agent_c': 'agent_c'
        },  # 映射表
    )

    # 隐式写法
    builder.add_conditional_edges(
        'agent_a',  # 执行 该节点
        route_agent_a  # 判断 'agent_a' 节点的输出 是否需要工具
    )
    # 显示写法
    builder.add_conditional_edges(
        'agent_b',
        route_agent_b,
        {
            'tool_node_b': 'tool_node_b',
            END: END
        }
    )
    builder.add_conditional_edges('agent_c', route_agent_c)

    # 工具执行后回到 指定节点
    builder.add_edge('tool_node_a', 'agent_a')  # 执行工具 -> 'agent_a' -> 'route_agent_a'
    builder.add_edge('tool_node_b', 'agent_b')
    builder.add_edge('tool_node_c', 'agent_c')

    return builder.compile(checkpointer=checkpointer)
