# 第五课：多 Agent 并发 — 让三个专家同时工作

> 复杂任务靠一个 Agent 串行处理太慢。
> LangGraph 的 Send API 可以把任务拆分给多个 Worker 并行执行，
> 就像 Huey 把多个任务分发给多个工作进程。

---

## 你已经知道的：Huey 异步任务

你的项目里用 Huey 处理异步任务：

```python
# 定义任务
@huey.task()
def send_report_email(client_id):
    # 查数据、生成报告、发邮件
    ...

@huey.task()
def update_risk_score(client_id):
    # 更新风险评分
    ...

# 同时触发多个任务，它们并行执行
send_report_email("C001")
update_risk_score("C001")
# 不等 send_report_email 完成就触发 update_risk_score
```

**LangGraph 的 Send API 做的是类似的事：把任务分发给多个 Agent Worker，让它们并行执行。**

---

## 什么时候需要多 Agent

单 Agent 串行处理"完整投资组合"任务：

```
查客户信息（0.5s）
    ↓
研究权益产品（2s，需要查基金数据 + 大模型分析）
    ↓
研究固收产品（2s，同上）
    ↓
分析市场环境（1.5s，查行情 + 大模型分析）
    ↓
合规检查（1s）
    ↓
生成最终建议（2s）

总计：约 9s
```

三个研究任务互相独立，完全可以并行：

```
查客户信息（0.5s）
    │
    ├──→ 研究权益产品（2s）  ──┐
    ├──→ 研究固收产品（2s）  ──┤  三个同时跑
    └──→ 分析市场环境（1.5s）──┘
                               │
                         合规检查（1s）
                               │
                        生成最终建议（2s）

总计：约 5.5s（节省 40%）
```

---

## LangGraph 的 Send API

`Send` 相当于 Huey 的 `.task()`——往一个节点发一个独立的任务包：

```python
from langgraph.constants import Send

def supervisor_node(state):
    """
    分发任务给三个 Worker，并行执行。
    返回 Send 列表，LangGraph 会自动并行调度它们。
    """
    client_id = state["client_id"]
    user_request = state["user_request"]
    
    # 先查客户信息（这个必须先做，后面三个 Worker 都需要）
    risk_info = query_client_risk_profile.invoke({"client_id": client_id})
    
    # 公共上下文，三个 Worker 都能读到
    base_context = {
        "client_id": client_id,
        "client_risk_level": risk_info["risk_level"],
        "user_request": user_request,
        "worker_results": [],
    }
    
    # 用 Send 派发三个任务——LangGraph 会并行执行
    return [
        Send("equity_researcher",        {**base_context, "task": "equity"}),
        Send("fixed_income_researcher",  {**base_context, "task": "fixed_income"}),
        Send("market_analyzer",          {**base_context, "task": "market"}),
    ]
```

**`supervisor_node` 不返回普通的 dict，而是返回 `Send` 列表。**
这是 LangGraph 的特殊语法，告诉框架"并行派发这些任务"。

---

## Worker 节点

每个 Worker 只做自己的事，不知道其他 Worker 在做什么：

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
import json

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)


async def equity_researcher_node(state):
    """专职研究权益类产品（股票型/混合型基金）"""
    risk_level = state["client_risk_level"]
    user_request = state["user_request"]

    prompt = f"""
你是权益类基金分析师。
客户风险等级：{risk_level}
客户需求：{user_request}

推荐 2-3 只权益类基金代码（股票型或混合型）。
格式：{{"products": ["代码1", "代码2"], "rationale": "理由"}}
只返回 JSON，不要其他内容。
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"products": [], "rationale": "解析失败"}

    # 关键：返回 worker_results 字段
    # LangGraph 会把三个 Worker 的 worker_results 自动合并为一个列表
    return {
        "worker_results": [{
            "type": "equity",
            "products": result.get("products", []),
            "rationale": result.get("rationale", ""),
        }]
    }


async def fixed_income_researcher_node(state):
    """专职研究固收类产品（债券/货币基金）"""
    risk_level = state["client_risk_level"]
    user_request = state["user_request"]

    prompt = f"""
你是固收产品分析师。
客户风险等级：{risk_level}
客户需求：{user_request}

推荐 2-3 只固收类产品（债券型或货币基金）。
格式：{{"products": ["代码1", "代码2"], "rationale": "理由"}}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"products": [], "rationale": "解析失败"}

    return {
        "worker_results": [{
            "type": "fixed_income",
            "products": result.get("products", []),
            "rationale": result.get("rationale", ""),
        }]
    }


async def market_analyzer_node(state):
    """专职分析当前市场环境"""
    # 查主要指数行情（假数据，实际调真实工具）
    market_data = {"沪指": 3200, "深成指": 10500, "沪深300": 3800}

    prompt = f"""
当前市场数据：{json.dumps(market_data, ensure_ascii=False)}

分析当前市场，给出：
1. 整体判断（偏强/震荡/偏弱）
2. 权益类建议仓位（百分比）
格式：{{"market_view": "...", "equity_position": 50}}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"market_view": "震荡", "equity_position": 50}

    return {
        "worker_results": [{
            "type": "market",
            "analysis": result,
        }]
    }
```

---

## Worker 结果如何合并：关键细节

三个 Worker 都返回 `{"worker_results": [...]}` ，但字段名相同，LangGraph 默认会用后面的**覆盖**前面的——这样就只剩一个 Worker 的结果了。

要告诉 LangGraph"这个字段要追加，不要覆盖"：

```python
import operator
from langgraph.graph import StateGraph

# 第二个参数：声明 worker_results 用 operator.add（列表相加 = 追加）
builder = StateGraph(dict, input={"worker_results": (list, operator.add)})
```

这样三个 Worker 的结果就会合并成一个列表：

```python
# Worker A 返回：{"worker_results": [{"type": "equity", ...}]}
# Worker B 返回：{"worker_results": [{"type": "fixed_income", ...}]}
# Worker C 返回：{"worker_results": [{"type": "market", ...}]}

# aggregate 节点收到的：
# state["worker_results"] == [
#     {"type": "equity", ...},
#     {"type": "fixed_income", ...},
#     {"type": "market", ...},
# ]
```

---

## 汇总节点：等所有 Worker 都完成

LangGraph 会自动等所有并行 Worker 完成后，才执行 `aggregate` 节点：

```python
def aggregate_node(state):
    """
    等三个 Worker 都跑完后，汇总结果。
    LangGraph 自动保证：只有三个 Worker 都完成了，这个节点才会执行。
    """
    worker_results = state.get("worker_results") or []
    
    # 从合并后的列表里分别提取三类结果
    equity = next((r for r in worker_results if r["type"] == "equity"), {})
    fixed = next((r for r in worker_results if r["type"] == "fixed_income"), {})
    market = next((r for r in worker_results if r["type"] == "market"), {})
    
    # 合并所有候选产品
    all_candidates = (
        equity.get("products", []) + fixed.get("products", [])
    )
    
    return {
        "candidate_products": all_candidates,
        "equity_research":    equity,
        "fixed_income_research": fixed,
        "market_analysis":    market,
    }
```

---

## 完整的图结构

```python
import operator
from langgraph.graph import StateGraph, END
from langgraph.constants import Send


def build_multi_agent_graph():
    # 声明 worker_results 用追加模式合并
    builder = StateGraph(dict, input={"worker_results": (list, operator.add)})
    
    # 注册节点
    builder.add_node("supervisor",              supervisor_node)
    builder.add_node("equity_researcher",       equity_researcher_node)
    builder.add_node("fixed_income_researcher", fixed_income_researcher_node)
    builder.add_node("market_analyzer",         market_analyzer_node)
    builder.add_node("aggregate",               aggregate_node)
    builder.add_node("compliance_gate",         compliance_gate_node)
    builder.add_node("portfolio_builder",       portfolio_builder_node)
    builder.add_node("audit_logging",           audit_logging_node)
    
    # supervisor 用 Send 并行派发
    builder.set_entry_point("supervisor")
    builder.add_conditional_edges("supervisor", lambda s: s, {})  # Send 自动处理路由
    
    # 三个 Worker 完成后汇聚到 aggregate
    builder.add_edge("equity_researcher",       "aggregate")
    builder.add_edge("fixed_income_researcher", "aggregate")
    builder.add_edge("market_analyzer",         "aggregate")
    
    # 后续串行
    builder.add_edge("aggregate",         "compliance_gate")
    builder.add_edge("compliance_gate",   "portfolio_builder")
    builder.add_edge("portfolio_builder", "audit_logging")
    builder.add_edge("audit_logging",     END)
    
    return builder.compile()
```

---

## 类比总结：多 Agent vs Huey 任务

| Huey 异步任务 | LangGraph 多 Agent |
|--------------|-------------------|
| `@huey.task()` | `async def worker_node(state)` |
| `task.delay(args)` | `Send("node_name", state)` |
| Worker 进程并行执行 | LangGraph 并行调度节点 |
| 任务结果写数据库 | Worker 返回 `{"worker_results": [...]}` |
| 主进程等所有任务完成 | `aggregate` 节点等所有 Worker 完成 |
| MemoryHuey（内存队列） | LangGraph 内部调度（无需外部队列） |

**核心差别：**
- Huey 任务结果写到外部存储（数据库/Redis），下游从存储里读
- LangGraph Worker 结果直接写进 state，下游节点直接从 state 读

LangGraph 把"任务分发 + 结果收集 + 流程编排"整合在一起，不需要外部队列。

---

## Worker 的设计原则

**Worker 只能调工具，不能再派发子任务。**

```python
# ✅ Worker 可以做的
async def equity_researcher_node(state):
    result = query_fund_nav.invoke({"fund_code": "000001"})   # 调工具
    response = await llm.ainvoke([...])                        # 调大模型
    return {"worker_results": [...]}

# ❌ Worker 不能做的
async def equity_researcher_node(state):
    return [Send("another_sub_worker", ...)]   # 不能再派发 Send
```

如果 Worker 可以再派 Worker，任务会无限嵌套，失控。
Worker 的工具清单里也不应该有能触发"派任务"的工具。

---

## 什么时候用多 Agent，什么时候用单 Agent

| 请求类型 | 推荐方案 | 原因 |
|---------|---------|------|
| "查000001净值" | 单 Agent（一个工具调用） | 没必要 Supervisor |
| "给客户推荐1-2个产品" | 单 Agent + 合规图（03的设计） | 复杂度不够 |
| "给我做完整投资组合" | **多 Agent**（本课） | 三类研究并行，明显提速 |
| "分析市场 + 推荐 + 组合" | **多 Agent** | 三类任务专业性不同 |
| "什么是ETF" | 直接 RAG 查知识库 | 连 Agent 都不需要 |

---

## 小结

```
多 Agent 解决的问题：
  复杂任务的多个子任务互相独立 → 并行执行 → 大幅减少等待时间

LangGraph Send API 用法：
  supervisor_node 返回 [Send("worker_name", state), ...]
  LangGraph 自动并行调度

Worker 结果合并：
  声明 worker_results 字段用 operator.add 追加合并
  aggregate 节点在所有 Worker 完成后自动执行

设计原则：
  Supervisor 只协调，不执行
  Worker 只执行，不再派发子任务
```

---

## 五课总结

| 课次 | 核心概念 | 类比 |
|------|---------|------|
| 01 | LLM 工具调用 = HTTP 请求/响应 | `httpx.post()` |
| 02 | AgentLoop = 带工具的循环推理 | Starlette 中间件链 |
| 03 | LangGraph State = 流程图 + 共享上下文 | `request` 对象 + 路由 |
| 04 | Callback = 透明监控观察者 | Starlette 中间件（只读） |
| 05 | 多 Agent = 并行任务分发 | Huey 异步任务队列 |

这五个概念组合在一起，就是 `docs/agent-design/` 里所有设计的底层支撑。
