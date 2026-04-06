# 第三课：LangGraph State — 用图来管理 AgentLoop

> 上一课的 `while True` 很清晰，但有一个大问题：
> 一旦流程复杂了（分支、合规检查、并发），while 循环就失控了。
> LangGraph 用"状态机"解决这个问题。

---

## 问题：while True 不够用

上一课的循环适合简单的查询任务。但投顾场景需要这样的流程：

```
收集客户信息
    ↓
大模型生成候选产品
    ↓
合规检查（必须过这关，不能跳过！）
    ↓
  ┌─── 通过 ───→ 生成推荐文字
  └─── 不通过 ──→ 生成拒绝原因
    ↓
审计日志（无论走哪条路都必须记录）
```

用 while True 写这个：

```python
# 这样写会很乱
while True:
    if step == "gather_info":
        result = gather_info(client_id)
        step = "llm_recommend"
    elif step == "llm_recommend":
        candidates = llm_recommend(result)
        step = "compliance"
    elif step == "compliance":
        passed, rejected = check_compliance(candidates)
        if passed:
            step = "generate_recommendation"
        else:
            step = "generate_rejection"
    elif step == "generate_recommendation":
        response = generate_recommendation(passed)
        step = "audit"
    # ... 越写越长，越写越乱
```

这是一个典型的状态机问题。你可能在 Huey 任务处理里见过类似的逻辑：
**根据当前状态决定下一步。**

---

## 你已经知道的：Starlette 的 Request 对象

你在 Starlette 里，`request` 对象贯穿整个请求生命周期：

```python
async def my_view(request):
    user_id = request.user.user_id      # 中间件填进去的
    body = await request.json()         # 请求体
    
    # 你写的业务逻辑可以随时从 request 里取数据
    ...
```

`request` 是整个请求生命周期里的"共享上下文"。

**LangGraph 的 `state` 就是 Agent 执行过程的"共享上下文"。**

---

## LangGraph 的核心思路

把上面那个流程图，直接用代码"画"出来：

```python
from langgraph.graph import StateGraph, END

builder = StateGraph(dict)   # state 就是一个普通 dict

# 把每个方框定义为一个函数（节点）
builder.add_node("info_gathering",          info_gathering_node)
builder.add_node("llm_recommend",           llm_recommend_node)
builder.add_node("compliance_gate",         compliance_gate_node)
builder.add_node("generate_recommendation", generate_recommendation_node)
builder.add_node("generate_rejection",      generate_rejection_node)
builder.add_node("audit_logging",           audit_logging_node)

# 把每条箭头定义为边
builder.set_entry_point("info_gathering")
builder.add_edge("info_gathering", "llm_recommend")
builder.add_edge("llm_recommend", "compliance_gate")

# 分支：根据 state 里的数据决定走哪条路
builder.add_conditional_edges(
    "compliance_gate",
    lambda state: "recommend" if state.get("approved_products") else "reject",
    {"recommend": "generate_recommendation", "reject": "generate_rejection"},
)

builder.add_edge("generate_recommendation", "audit_logging")
builder.add_edge("generate_rejection", "audit_logging")
builder.add_edge("audit_logging", END)

graph = builder.compile()
```

这就是整个投顾合规流程的完整定义。代码和流程图是同构的。

---

## State：节点之间的"传话筒"

每个节点函数接收 `state`（dict），返回对 state 的更新：

```python
async def info_gathering_node(state):
    # 从 state 里读取输入
    client_id = state["client_id"]
    
    # 做实际工作
    risk_result = query_client_risk_profile.invoke({"client_id": client_id})
    
    # 返回对 state 的更新（只需要写"有变化的部分"）
    return {
        "client_risk_level": risk_result["risk_level"],
        "risk_is_expired": risk_result["is_expired"],
    }


async def compliance_gate_node(state):
    # 读取上一个节点写进 state 的数据
    candidates = state.get("candidate_products") or []
    client_id = state["client_id"]
    
    approved = []
    rejected = []
    
    for product_code in candidates:
        result = check_product_suitability.invoke({
            "client_id": client_id,
            "product_code": product_code,
        })
        if result["is_suitable"]:
            approved.append(product_code)
        else:
            rejected.append(product_code)
    
    # 后续节点和条件边都会读这两个字段
    return {
        "approved_products": approved,
        "rejected_products": rejected,
    }
```

**规则：每个节点只负责往 state 里写自己的输出，不需要关心其他节点的逻辑。**

---

## 完整示例：一个能跑的最小合规图

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)


# ── 节点函数 ──────────────────────────────────────────────────

def info_gathering_node(state):
    """查询客户信息（这里用假数据代替真实 DB 查询）"""
    client_id = state["client_id"]
    
    # 假设查询结果
    risk_data = {"C001": "C3", "C002": "C1"}.get(client_id, "C3")
    
    return {"client_risk_level": risk_data}


async def llm_recommend_node(state):
    """让大模型根据风险等级推荐候选产品"""
    risk_level = state["client_risk_level"]
    user_msg = state["messages"][-1].content
    
    prompt = f"""
客户风险等级：{risk_level}
客户需求：{user_msg}

推荐 2 个适合该风险等级的基金代码。
只返回 JSON 数组，例如：["000001", "110011"]
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    import json, re
    match = re.search(r'\[.*?\]', response.content)
    candidates = json.loads(match.group()) if match else []
    
    return {"candidate_products": candidates}


def compliance_gate_node(state):
    """合规检查（简化版：只检查风险匹配）"""
    candidates = state.get("candidate_products") or []
    risk_level = state["client_risk_level"]
    
    # 假设 C1/C2 客户不能买 R4/R5 产品，简化处理
    approved = []
    rejected = []
    
    for code in candidates:
        # 实际环境里调真实的合规工具
        if risk_level in ("C1", "C2") and code.startswith("1"):
            rejected.append(code)   # 假设 1 开头的是高风险产品
        else:
            approved.append(code)
    
    return {
        "approved_products": approved,
        "rejected_products": rejected,
    }


async def generate_recommendation_node(state):
    """生成推荐文字"""
    approved = state["approved_products"]
    risk_level = state["client_risk_level"]
    
    prompt = f"客户风险等级 {risk_level}，已通过合规的产品是 {approved}，请用专业语言介绍推荐理由。"
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    return {"final_response": response.content}


def generate_rejection_node(state):
    """生成拒绝说明"""
    rejected = state.get("rejected_products") or []
    risk_level = state["client_risk_level"]
    
    return {
        "final_response": f"抱歉，根据您的风险等级（{risk_level}），以下产品不适合您：{rejected}。"
    }


def audit_logging_node(state):
    """审计日志（所有路径都必须经过）"""
    import json
    record = {
        "client_id": state["client_id"],
        "approved": state.get("approved_products"),
        "rejected": state.get("rejected_products"),
    }
    print(f"[AUDIT] {json.dumps(record, ensure_ascii=False)}")
    return {}   # 不需要更新 state，返回空 dict


# ── 构建图 ────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(dict)
    
    builder.add_node("info_gathering",          info_gathering_node)
    builder.add_node("llm_recommend",           llm_recommend_node)
    builder.add_node("compliance_gate",         compliance_gate_node)
    builder.add_node("generate_recommendation", generate_recommendation_node)
    builder.add_node("generate_rejection",      generate_rejection_node)
    builder.add_node("audit_logging",           audit_logging_node)
    
    builder.set_entry_point("info_gathering")
    builder.add_edge("info_gathering", "llm_recommend")
    builder.add_edge("llm_recommend", "compliance_gate")
    
    builder.add_conditional_edges(
        "compliance_gate",
        lambda s: "recommend" if s.get("approved_products") else "reject",
        {"recommend": "generate_recommendation", "reject": "generate_rejection"},
    )
    
    builder.add_edge("generate_recommendation", "audit_logging")
    builder.add_edge("generate_rejection", "audit_logging")
    builder.add_edge("audit_logging", END)
    
    return builder.compile()


graph = build_graph()


# ── 使用 ──────────────────────────────────────────────────────

import asyncio
from langchain_core.messages import HumanMessage

async def main():
    result = await graph.ainvoke({
        "messages": [HumanMessage(content="帮我推荐适合的基金产品")],
        "client_id": "C001",
        "audit_log": [],
    })
    print(result["final_response"])

asyncio.run(main())
```

---

## 关键对比：while True vs LangGraph

| 维度 | 手写 while True | LangGraph |
|------|----------------|-----------|
| 流程结构 | 隐藏在 if/elif 里 | 显式定义为图，可视化 |
| 合规保证 | 靠程序员自己记得加检查 | 节点是图的结构，绕不过去 |
| 分支逻辑 | 手动 if/else | `add_conditional_edges` |
| 状态传递 | 一堆局部变量 | 统一 state dict |
| 扩展性 | 加新步骤要改循环主体 | 加节点 + 加边，其他不动 |

---

## 一个容易犯的错误：节点函数不能直接修改 state

```python
# ❌ 错误写法：直接修改 state dict
def my_node(state):
    state["result"] = "something"   # 千万别这样
    return state

# ✅ 正确写法：返回更新的部分
def my_node(state):
    return {"result": "something"}   # 只返回变化的字段
```

LangGraph 内部用返回值来合并 state，直接修改会引发不可预期的问题。

---

## State 也是 Agent 的"短期记忆"

每次 `graph.invoke()` 都是一个独立的 state。
如果你想跨多轮对话保留上下文（比如客户和 Agent 聊了多条消息），
需要用 **LangGraph Checkpointer**：

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 每次调用传同一个 thread_id，LangGraph 会自动加载上次的 state
config = {"configurable": {"thread_id": "client_C001_session_1"}}

result1 = await graph.ainvoke(state1, config=config)
result2 = await graph.ainvoke(state2, config=config)   # 能看到 result1 的上下文
```

每个客户一个 `thread_id`，对话上下文隔离，不会串。

---

## 小结

```
LangGraph 把 AgentLoop 从：
  while True → if step == "xxx" → ...

变成了：
  节点（函数）+ 边（连线）+ 条件边（分支）

State（dict）是节点间的共享数据，每个节点读取输入、写回输出。

合规节点写在图的结构里，大模型改不了、用户绕不过。
```

下一课：[04 - Callback：像中间件一样监控 Agent 的每一步](./04-callback.md)
