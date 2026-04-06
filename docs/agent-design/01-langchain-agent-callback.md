# LangChain Agent + Callback 体系详解

> 面向有 Python 后端经验、初次接触 AI Agent 工程的工程师。

---

## 第一部分：AgentLoop 是什么

### 1.1 问题的本质

大模型（Claude、GPT-4）本质上是一个**无状态函数**：

```python
response = llm.invoke("帮我查一下基金 000001 的净值")
# 返回："好的，基金 000001 的净值是..." ← 纯文字，它根本没真正查过
```

它只会说话，不会做事。就像一个聪明的顾问，但没有电脑，什么都查不了。

**Agent 解决的就是这个问题**：给大模型配上"工具"，让它能真正去查数据、调 API、做计算。

### 1.2 AgentLoop 的核心就是一个 while 循环

```python
# AgentLoop 的本质
while True:
    # 第一步：问大模型，接下来该做什么
    response = llm_with_tools.invoke(messages)

    # 第二步：大模型说要调用工具？执行它
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = tools[tool_call["name"]].invoke(tool_call["args"])
            messages.append(ToolMessage(result))
    else:
        # 第三步：大模型没有要调用的工具了，任务完成
        break
```

就这三步，反复循环。这个模式有个正式名字叫 **ReAct**（Reasoning + Acting）。

---

## 第二部分：LangChain 四大核心概念

### 2.1 概念一：Tool（工具）

工具就是你写的普通 Python 函数，加一个 `@tool` 装饰器。

```python
from langchain_core.tools import tool

@tool
def query_fund_nav(fund_code, date=None):
    """
    查询基金的单位净值。
    fund_code: 基金代码，如 '000001'。
    date: 查询日期 YYYY-MM-DD，不填则返回最新净值。
    """
    # 这里是真正的实现：查数据库或调外部 API
    return {"fund_code": fund_code, "nav": 1.2345, "date": "2026-04-03"}
```

**关键点：docstring 是写给大模型看的，不是给人看的。**

大模型靠 docstring 决定什么时候调用这个工具，以及每个参数是什么意思。
写得不清楚，大模型不知道什么时候该用，或者乱传参数。

**工具的本质是什么：**
LangChain 把你这个 Python 函数转成 JSON 格式，告诉大模型 API：
"你可以调用这些工具，每个工具叫什么名字、干什么用、需要什么参数"。
大模型的回复里会说："我要调用 `query_fund_nav`，参数是 `{'fund_code': '000001'}`"。
你的代码收到这个，就去真正执行这个 Python 函数，把结果再返回给大模型。

### 2.2 概念二：LLM with Tools（绑定工具的大模型）

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")

# 把工具列表"告诉"大模型
llm_with_tools = llm.bind_tools([
    query_fund_nav,
    query_client_risk_profile,
    check_product_suitability,
    # ... 其他工具
])
```

`bind_tools` 之后，大模型就知道它可以使用这些工具了。

### 2.3 概念三：AgentExecutor vs LangGraph

**AgentExecutor（旧方式，不用）：**

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
result = executor.invoke({"input": "帮我推荐一个适合保守型投资者的产品"})
```

这个方式里大模型是完全自由的，可以不调任何工具直接输出建议。
对于银行合规场景，这不可接受。

**LangGraph（用这个）：**

LangGraph 让你把流程定义成一张图，每个步骤是一个节点，大模型必须按图走。

```python
from langgraph.graph import StateGraph, END

# 节点：每个节点就是一个处理函数
def call_llm(state):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}

def run_tools(state):
    last_message = state["messages"][-1]
    results = []
    for tool_call in last_message.tool_calls:
        output = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        results.append(ToolMessage(content=str(output), tool_call_id=tool_call["id"]))
    return {"messages": state["messages"] + results}

# 路由：决定下一步去哪个节点
def should_continue(state):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "run_tools"
    return END

# 构建图
builder = StateGraph(dict)
builder.add_node("call_llm", call_llm)
builder.add_node("run_tools", run_tools)
builder.set_entry_point("call_llm")
builder.add_conditional_edges("call_llm", should_continue)
builder.add_edge("run_tools", "call_llm")   # 工具结果返回给大模型继续思考

graph = builder.compile()
```

图的结构：
```
[call_llm] ──有工具调用──→ [run_tools] ──→ [call_llm]（循环）
    │
    没有工具调用
    │
    ▼
   END
```

大模型只能按这条路走，加一个合规检查节点，它就必须经过。

### 2.4 概念四：Callback（回调/钩子）

Callback 就是在执行的各个阶段插入你自己的代码：大模型调用前后、工具执行前后。
用途：审计日志、性能监控、合规违规检测。

```python
from langchain_core.callbacks import AsyncCallbackHandler
from datetime import datetime

class AuditCallback(AsyncCallbackHandler):

    def __init__(self, conversation_id, advisor_id):
        self.conversation_id = conversation_id
        self.advisor_id = advisor_id
        self.records = []

    # 工具开始执行前触发
    async def on_tool_start(self, serialized, input_str, **kwargs):
        self.records.append({
            "event": "tool_start",
            "tool": serialized.get("name"),
            "input": input_str,
            "time": datetime.utcnow().isoformat(),
        })

    # 工具执行完触发
    async def on_tool_end(self, output, **kwargs):
        if self.records:
            self.records[-1]["output"] = str(output)[:200]

    # 大模型回复完触发
    async def on_llm_end(self, response, **kwargs):
        content = response.generations[0][0].text
        # 检测大模型是否绕过工具直接给出建议（合规风险）
        has_direct_advice = any(kw in content for kw in ["推荐买入", "建议申购", "建议加仓"])
        if has_direct_advice:
            self.records.append({
                "event": "compliance_alert",
                "reason": "LLM 未调用合规工具直接输出投资建议",
                "time": datetime.utcnow().isoformat(),
            })
```

**使用方式：**

```python
audit_cb = AuditCallback(
    conversation_id="conv-001",
    advisor_id=request.user.user_id,
)

result = graph.invoke(
    {"messages": [HumanMessage(content=user_input)]},
    config={"callbacks": [audit_cb]}   # ← 传入 callback
)

# 执行完之后保存审计记录
await audit_cb.save_to_db()
```

---

## 第三部分：LangChain 生态的包结构

安装时你会看到好几个 `langchain-*` 包，容易搞混：

```
langchain 生态
├── langchain-core          ← 最底层接口（BaseTool、BaseMessage 等）
├── langchain-anthropic     ← Claude 专用（ChatAnthropic）
├── langchain-openai        ← OpenAI 专用（ChatOpenAI）
├── langgraph               ← 状态机 Agent 框架（你要用的核心）
└── langchain               ← 高层封装（AgentExecutor 在这里，基本不用了）
```

**你只需要安装这几个：**

```bash
pip install langgraph langchain-core langchain-anthropic
```

---

## 第四部分：流式输出（SSE）

投顾场景需要"打字机效果"，LangGraph 支持流式，和 Starlette SSE 配合：

```python
from starlette.responses import StreamingResponse
import json

async def agent_stream_view(request):
    body = await request.json()
    user_input = body["message"]
    client_id = body["client_id"]

    async def event_stream():
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content=user_input)], "client_id": client_id},
            stream_mode="values",
        ):
            # 每次图状态更新时触发
            if chunk.get("final_response"):
                data = json.dumps({"content": chunk["final_response"]}, ensure_ascii=False)
                yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## 第五部分：会话记忆

大模型是无状态的，"记住上下文"需要把历史消息传进去。
LangGraph 用 `Checkpointer` 自动管理：

```python
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string("./dev_checkpoints.db") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)

    # 同一个 thread_id 的调用自动带上历史
    config = {"configurable": {"thread_id": f"client_{client_id}"}}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="帮我推荐一个产品")]},
        config=config
    )
    # 下一次用同一个 thread_id 调用，会话历史自动延续
```

生产环境可以换成 MySQL 或 Redis 的 Checkpointer（LangGraph 支持自定义实现）。

---

## 第六部分：最简完整示例

把上面所有概念串起来，能跑通的最小 Agent：

```python
# src/domains/agent/graph.py

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END


# ── 1. 定义工具 ──────────────────────────────────────────────
@tool
def query_fund_nav(fund_code):
    """查询基金当前净值。fund_code: 基金代码如 '000001'。推荐基金前必须先查净值。"""
    return {"fund_code": fund_code, "nav": 1.2345, "date": "2026-04-03"}


@tool
def query_client_risk(client_id):
    """查询客户风险承受能力等级（保守型/稳健型/积极型）。生成投资建议前必须先调用。"""
    return {"client_id": client_id, "risk_level": "稳健型", "score": 65}


tools = [query_fund_nav, query_client_risk]
tools_by_name = {t.name: t for t in tools}


# ── 2. 初始化 LLM ────────────────────────────────────────────
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
llm_with_tools = llm.bind_tools(tools)


# ── 3. 定义节点 ──────────────────────────────────────────────
def call_llm(state):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}


def run_tools(state):
    last_message = state["messages"][-1]
    results = []
    for tool_call in last_message.tool_calls:
        output = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        results.append(
            ToolMessage(content=str(output), tool_call_id=tool_call["id"])
        )
    return {"messages": state["messages"] + results}


# ── 4. 路由函数 ──────────────────────────────────────────────
def should_continue(state):
    if state["messages"][-1].tool_calls:
        return "run_tools"
    return END


# ── 5. 构建图 ────────────────────────────────────────────────
builder = StateGraph(dict)
builder.add_node("call_llm", call_llm)
builder.add_node("run_tools", run_tools)
builder.set_entry_point("call_llm")
builder.add_conditional_edges("call_llm", should_continue)
builder.add_edge("run_tools", "call_llm")

graph = builder.compile()


# ── 6. 运行 ──────────────────────────────────────────────────
if __name__ == "__main__":
    result = graph.invoke({
        "messages": [HumanMessage(content="客户ID是C001，帮我推荐一个适合他的基金")]
    })
    print(result["messages"][-1].content)
```

---

## 总结

| 概念 | 是什么 | 怎么用 |
|------|--------|--------|
| Tool | 带 `@tool` 装饰器的普通函数 | docstring 写清楚，大模型靠它判断用不用 |
| LLM with Tools | `llm.bind_tools(tools)` | 把工具列表告诉大模型 |
| LangGraph 节点 | 普通函数，接收 state 返回 state 更新 | 每个节点做一件事 |
| 条件边 | 路由函数，返回下一个节点名 | 实现 if/else 流程控制 |
| Callback | 继承 `AsyncCallbackHandler` 的类 | 在各阶段插入审计/监控逻辑 |
