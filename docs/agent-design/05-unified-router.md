# 统一入口：意图路由设计

> 用户只有一个对话入口，但请求类型差异很大。
> 解决办法是在图的最前面加一个路由节点，让它判断意图，再分叉到不同的处理路径。

---

## 一、问题描述

用户的请求可能是这四类中的任何一种：

| 类型 | 示例 | 需要什么 |
|------|------|---------|
| `knowledge` | "什么是可转债？" | 直接查知识库回答，不需要任何工具，不需要合规 |
| `query` | "帮我查一下 000001 的净值" | 一两个工具调用，不需要合规检查 |
| `recommend` | "给客户 C001 推荐一个产品" | 单 Agent + 合规检查（03 的设计） |
| `portfolio` | "给客户 C001 做一个完整的投资组合" | 多 Agent Supervisor（04 的设计） |

只有一个 HTTP 入口，怎么兼容这四种情况？

---

## 二、解决方案：图内部路由

**不要在 HTTP 层做判断，把路由逻辑放进图里。**

HTTP 入口永远调同一个图。图的第一个节点是路由节点，它负责判断意图，然后通过条件边分叉到不同路径。

```
用户请求（无论什么类型）
    │
    ▼
[intent_router] ← 用大模型判断意图（用便宜快的 Haiku）
    │
    ├── knowledge  ──→ [rag_answer] ──→ [audit] ──→ END
    │
    ├── query      ──→ [direct_query] ──→ [audit] ──→ END
    │
    ├── recommend  ──→ [single_agent 流程（03）] ──→ [audit] ──→ END
    │
    └── portfolio  ──→ [multi_agent 流程（04）] ──→ [audit] ──→ END
```

四条路径最终都汇聚到同一个 `audit_logging` 节点，保证审计日志无论走哪条路都会被记录。

---

## 三、路由节点的设计

路由节点做的事只有一件：判断意图，返回一个分类词。

**关键：用便宜的快速模型（Haiku），不要用 Sonnet。**
路由判断本身很简单，用贵的模型是浪费，而且会增加延迟。

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

# 路由专用，用快速便宜的模型
router_llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

# 后续节点用的正式模型
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)


def intent_router_node(state):
    """
    判断用户意图，返回四种分类之一。
    这是整个图的入口节点，决定后续走哪条路径。
    """
    user_input = state["messages"][-1].content

    prompt = f"""你是一个请求分类器，把用户的投资理财相关请求分类为以下四种之一：

knowledge  - 用户想了解金融知识或概念（什么是XX，如何理解XX）
query      - 用户查询具体数据（净值、行情、持仓、交易记录等）
recommend  - 用户要求为客户推荐1-3个具体产品
portfolio  - 用户要求构建完整投资组合或资产配置方案

用户请求：{user_input}

只返回一个词：knowledge、query、recommend 或 portfolio。不要任何解释。"""

    response = router_llm.invoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()

    # 防御：如果大模型返回了不认识的词，默认走 recommend（最常见路径）
    if intent not in ("knowledge", "query", "recommend", "portfolio"):
        intent = "recommend"

    return {"intent": intent}


def route_by_intent(state):
    """条件边的路由函数，根据 intent 返回下一个节点名。"""
    return state.get("intent", "recommend")
```

---

## 四、四条路径的节点实现

### 路径 A：knowledge — 知识问答

最简单的路径，直接查知识库，大模型组织回答，不需要合规。

```python
async def rag_answer_node(state):
    user_input = state["messages"][-1].content

    # 查知识库
    docs = search_investment_knowledge.invoke({"query": user_input})

    context = "\n\n".join(d["content"] for d in docs) if docs else "知识库中暂无相关内容。"

    prompt = f"""根据以下知识库内容，回答用户的问题。
如果知识库内容不足以回答，请如实说明，不要编造。

知识库内容：
{context}

用户问题：{user_input}"""

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return {"final_response": response.content}
```

### 路径 B：query — 数据查询

直接用工具查数据，格式化后返回，不需要合规检查。

```python
async def direct_query_node(state):
    user_input = state["messages"][-1].content
    client_id = state.get("client_id", "")

    # 给大模型工具，让它自己判断调哪个
    query_tools = [query_fund_nav, query_market_data, query_client_holdings, query_product_info]
    llm_with_query_tools = llm.bind_tools(query_tools)

    messages = list(state["messages"])

    # 简单的 ReAct 循环，最多跑 3 轮（查询请求不会太复杂）
    for _ in range(3):
        response = await llm_with_query_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_fn = {t.name: t for t in query_tools}.get(tool_call["name"])
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

    return {
        "final_response": messages[-1].content,
        "messages": messages,
    }
```

### 路径 C：recommend — 单产品推荐

复用 `03` 里设计的合规流程。这里不重复写节点实现，直接把 03 的子图嵌进来。

```python
from .graph import build_single_agent_subgraph

# 03 里的完整流程作为子图
single_agent_subgraph = build_single_agent_subgraph()
```

### 路径 D：portfolio — 完整组合

复用 `04` 里的多 Agent 流程。

```python
from .multi_agent_graph import build_multi_agent_subgraph

multi_agent_subgraph = build_multi_agent_subgraph()
```

---

## 五、组装成一张完整的图

```python
# src/domains/agent/unified_graph.py

import operator
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END

from .tools import (
    search_investment_knowledge,
    query_fund_nav, query_market_data, query_client_holdings, query_product_info,
)
from .graph import (
    info_gathering_node,
    llm_recommend_node,
    compliance_gate_node,
    generate_recommendation_node,
    generate_rejection_node,
)
from .multi_agent_graph import (
    supervisor_node,
    equity_researcher_node,
    fixed_income_researcher_node,
    market_analyzer_node,
    aggregate_node,
    portfolio_builder_node,
)
from .router import intent_router_node, route_by_intent, rag_answer_node, direct_query_node
from .callbacks import audit_logging_node


def build_unified_graph():
    builder = StateGraph(dict)

    # ── 路由节点（入口）──────────────────────────────────────
    builder.add_node("intent_router", intent_router_node)

    # ── 路径 A：knowledge ─────────────────────────────────────
    builder.add_node("rag_answer", rag_answer_node)

    # ── 路径 B：query ─────────────────────────────────────────
    builder.add_node("direct_query", direct_query_node)

    # ── 路径 C：recommend（03 的节点）─────────────────────────
    builder.add_node("info_gathering", info_gathering_node)
    builder.add_node("llm_recommend", llm_recommend_node)
    builder.add_node("compliance_gate", compliance_gate_node)
    builder.add_node("generate_recommendation", generate_recommendation_node)
    builder.add_node("generate_rejection", generate_rejection_node)

    # ── 路径 D：portfolio（04 的节点）─────────────────────────
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("equity_researcher", equity_researcher_node)
    builder.add_node("fixed_income_researcher", fixed_income_researcher_node)
    builder.add_node("market_analyzer", market_analyzer_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("portfolio_builder", portfolio_builder_node)

    # ── 审计节点（所有路径共用）──────────────────────────────
    builder.add_node("audit_logging", audit_logging_node)

    # ── 连边：入口路由 ────────────────────────────────────────
    builder.set_entry_point("intent_router")
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "knowledge":  "rag_answer",
            "query":      "direct_query",
            "recommend":  "info_gathering",    # 路径 C 的起点
            "portfolio":  "supervisor",         # 路径 D 的起点
        },
    )

    # ── 连边：路径 A ──────────────────────────────────────────
    builder.add_edge("rag_answer", "audit_logging")

    # ── 连边：路径 B ──────────────────────────────────────────
    builder.add_edge("direct_query", "audit_logging")

    # ── 连边：路径 C（和 03 里完全一样）──────────────────────
    builder.add_edge("info_gathering", "llm_recommend")
    builder.add_edge("llm_recommend", "compliance_gate")
    builder.add_conditional_edges(
        "compliance_gate",
        lambda s: "recommend" if s.get("approved_products") else "reject",
        {"recommend": "generate_recommendation", "reject": "generate_rejection"},
    )
    builder.add_edge("generate_recommendation", "audit_logging")
    builder.add_edge("generate_rejection", "audit_logging")

    # ── 连边：路径 D（和 04 里完全一样）──────────────────────
    builder.add_conditional_edges("supervisor", lambda s: s, {})   # Send API
    builder.add_edge("equity_researcher", "aggregate")
    builder.add_edge("fixed_income_researcher", "aggregate")
    builder.add_edge("market_analyzer", "aggregate")
    builder.add_edge("aggregate", "compliance_gate")    # 复用同一个合规节点
    builder.add_edge("portfolio_builder", "audit_logging")

    # ── 所有路径的终点 ────────────────────────────────────────
    builder.add_edge("audit_logging", END)

    return builder.compile()


unified_graph = build_unified_graph()
```

---

## 六、视图层不需要任何判断

HTTP 入口只做一件事：把请求扔给图。

```python
# src/domains/agent/views.py

import uuid, json
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.authentication import requires
from langchain_core.messages import HumanMessage

from src.core.response import fail
from src.core.codes import BizCode
from .unified_graph import unified_graph
from .callbacks import FinancialAuditCallback


@requires("authenticated")
async def agent_stream_view(request):
    body = await request.json()
    user_input = body.get("message", "").strip()
    client_id = body.get("client_id", "").strip()

    if not client_id:
        return fail(BizCode.PARAM_MISSING)

    conversation_id = str(uuid.uuid4())
    audit_cb = FinancialAuditCallback(
        conversation_id=conversation_id,
        advisor_id=request.user.user_id,
        client_id=client_id,
    )

    async def event_stream():
        try:
            async for chunk in unified_graph.astream(
                {
                    "messages": [HumanMessage(content=user_input)],
                    "client_id": client_id,
                    "conversation_id": conversation_id,
                    "audit_log": [],
                    # intent 不需要传，路由节点自己判断
                },
                config={"callbacks": [audit_cb]},
                stream_mode="values",
            ):
                if chunk.get("final_response"):
                    data = json.dumps(
                        {"content": chunk["final_response"]},
                        ensure_ascii=False,
                    )
                    yield f"data: {data}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## 七、路由判断的准确性

纯靠大模型分类会有误判，有几种方式可以提升准确率：

### 方式 A：规则优先，大模型兜底

对特别明确的请求直接用规则判断，只有模糊的才交给大模型：

```python
def intent_router_node(state):
    user_input = state["messages"][-1].content

    # 规则判断：明确的 query 类请求
    query_keywords = ["净值", "行情", "持仓", "多少钱", "涨跌", "价格"]
    if any(kw in user_input for kw in query_keywords) and "推荐" not in user_input:
        return {"intent": "query"}

    # 规则判断：明确的 portfolio 类请求
    portfolio_keywords = ["投资组合", "资产配置", "整体规划", "全部资产"]
    if any(kw in user_input for kw in portfolio_keywords):
        return {"intent": "portfolio"}

    # 规则判断：明确的知识类请求
    knowledge_keywords = ["什么是", "如何理解", "解释一下", "是什么意思"]
    if any(kw in user_input for kw in knowledge_keywords):
        return {"intent": "knowledge"}

    # 模糊情况，交给大模型
    response = router_llm.invoke([HumanMessage(content=ROUTER_PROMPT.format(input=user_input))])
    intent = response.content.strip().lower()

    if intent not in ("knowledge", "query", "recommend", "portfolio"):
        intent = "recommend"

    return {"intent": intent}
```

### 方式 B：让前端传 hint

如果前端界面上有固定按钮（"帮我推荐产品" / "规划投资组合"），前端直接传分类，后端优先用前端传的：

```python
def intent_router_node(state):
    # 前端明确传了 intent，直接用
    client_hint = state.get("client_hint")
    if client_hint in ("knowledge", "query", "recommend", "portfolio"):
        return {"intent": client_hint}

    # 前端没传，用大模型判断
    ...
```

视图层对应改一行：
```python
# views.py 里 graph.astream 的初始 state 加一个字段
"client_hint": body.get("intent_hint", ""),   # 前端可选传，也可以不传
```

---

## 八、整体架构最终全景

结合 01-05 所有文档，完整架构是这样的：

```
HTTP POST /api/v1/agent/stream
    │
    ▼
unified_graph（一张图）
    │
    ▼
[intent_router]  ← Haiku 快速分类（约 300ms）
    │
    ├── knowledge ──→ [rag_answer] ──────────────────────────────┐
    │                                                             │
    ├── query ──────→ [direct_query] ─────────────────────────── │
    │                                                             │
    ├── recommend ──→ [info_gathering]                            │
    │                    → [llm_recommend]                        │
    │                    → [compliance_gate] ← ── ── ── ── ──    │
    │                    → [generate_recommendation/rejection]    │
    │                                                  │          │
    └── portfolio ──→ [supervisor]                     │          │
                         ├─→ [equity_researcher]       │          │
                         ├─→ [fixed_income_researcher] │          │
                         └─→ [market_analyzer]         │          │
                              → [aggregate]            │          │
                              → [compliance_gate] ─────┘          │
                              → [portfolio_builder]               │
                                    │                             │
                                    └──────────────────┬──────────┘
                                                       ▼
                                              [audit_logging]
                                                       │
                                                      END
```

所有路径都经过 `audit_logging`，合规 `compliance_gate` 节点被 recommend 和 portfolio 两条路复用。
