from typing import Literal

from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode

from src.ai.core.llm_registry import llm_registry


class GameState(MessagesState):
    next: str


@tool
def search_web(query: str) -> str:
    """在互联网上搜索最新资讯、新闻、实时数据"""
    # TODO: 接入真实搜索 API，如 Tavily / Bing Search
    return f"[搜索结果] 关键词「{query}」的相关内容：..."


@tool
def calculate(expression: str) -> str:
    """安全地计算数学表达式，支持四则运算"""
    try:
        # 生产环境建议使用 numexpr 替代 eval
        result = eval(expression, {"__builtins__": {}})
        return f"[计算结果] {expression} = {result}"
    except Exception as e:
        return f"[计算错误] {e}"


@tool
def query_database(sql: str) -> str:
    """查询业务数据库，获取订单、用户、库存等结构化数据"""
    # TODO: 接入真实业务数据库
    return f"[数据库查询] SQL: {sql} → 返回结果：..."


supervisor_agent_prompt = """\
你是一位专业的分析人员，给输入的问题做分类，根据对话上下文选择下一步处理对象，放入next字段。

###next字段分类###
- agent_a：擅长 [网络搜索 + 数学计算]，适合查询实时信息或做数值推导
- agent_b：擅长 [数学计算 + 数据库查询]，适合结合业务数据做统计分析
- agent_c：擅长 [网络搜索 + 数据库查询]，适合结合外部资讯与内部数据综合回答

###返回格式###
返回格式仅返回 JSON: {{"next":"..."}}
"""

agent_a_system_prompt = """\
你是一个智能助手，具备网络搜索和数学计算能力。
请根据用户的问题和对话历史，合理调用工具，给出准确完整的回答。
"""

agent_b_system_prompt = """\
你是一个智能助手，具备数学计算和业务数据库查询能力。
请根据用户的问题和对话历史，合理调用工具，给出准确完整的回答。
"""

agent_c_system_prompt = """\
你是一个智能助手，具备网络搜索和业务数据库查询能力。
请根据用户的问题和对话历史，合理调用工具，给出准确完整的回答。
"""


class RouterOutput(BaseModel):
    next: Literal['agent_a', 'agent_b', 'agent_c']


# 主 Agent
def supervisor_node(state: GameState) -> dict:
    # last_user_msg = state['messages'][-1]
    recent_message_limit = 6  # 最近的 3 轮问答
    recent_messages = state['messages'][-recent_message_limit:]

    llm = llm_registry['common']
    structured_supervisor_llm = llm.with_structured_output(RouterOutput)  # 绑定 结构化 输出

    routing = structured_supervisor_llm.invoke([
        SystemMessage(content=supervisor_agent_prompt),
        # last_user_msg,
        *recent_messages,
    ])
    return {'next': routing.next}


# 子 Agent
def agent_a_node(state: GameState):
    tools = [search_web, calculate]

    llm = llm_registry['common']
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=agent_a_system_prompt)] + state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}


def agent_b_node(state: GameState):
    tools = [calculate, query_database]

    llm = llm_registry['common']
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=agent_b_system_prompt)] + state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}


def agent_c_node(state: GameState):
    tools = [search_web, query_database]

    llm = llm_registry['common']
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=agent_c_system_prompt)] + state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}


# ToolNode 实际 执行工具
tool_node_a = ToolNode([search_web, calculate])
tool_node_b = ToolNode([calculate, query_database])
tool_node_c = ToolNode([search_web, query_database])


# 条件路由
def route_supervisor(state: GameState) -> str:
    return state['next']


def route_agent_a(state: GameState) -> str:
    last = state['messages'][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return 'tool_node_a'
    return END


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


def build_game_graph():
    builder = StateGraph(GameState)  # noqa

    builder.add_node('supervisor', supervisor_node)  # noqa
    builder.add_node('agent_a', agent_a_node)  # noqa
    builder.add_node('agent_b', agent_b_node)  # noqa
    builder.add_node('agent_c', agent_c_node)  # noqa
    builder.add_node('tool_node_a', tool_node_a)
    builder.add_node('tool_node_b', tool_node_b)
    builder.add_node('tool_node_c', tool_node_c)

    builder.add_edge(START, 'supervisor')

    builder.add_conditional_edges(
        'supervisor',
        route_supervisor,
        {
            'agent_a': 'agent_a',
            'agent_b': 'agent_b',
            'agent_c': 'agent_c'
        },
    )

    builder.add_conditional_edges('agent_a', route_agent_a)
    builder.add_conditional_edges('agent_b', route_agent_b)
    builder.add_conditional_edges('agent_c', route_agent_c)

    builder.add_edge('tool_node_a', 'agent_a')
    builder.add_edge('tool_node_b', 'agent_b')
    builder.add_edge('tool_node_c', 'agent_c')

    graph = builder.compile()
    return graph
