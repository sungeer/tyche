# 多 Agent 协作：Supervisor 模式

> 单个 Agent 处理复杂请求时会很慢，且上下文容易混乱。
> 多 Agent 把任务拆开，让专职 Worker 并行干活，Supervisor 负责协调和汇总。

---

## 一、什么时候需要多 Agent

单 Agent 足够应对简单请求：
```
"帮我查一下000001的净值"  →  一个工具调用，直接返回
```

但遇到这类请求，单 Agent 就吃力了：
```
"我有50万，请帮我做一个完整的投资组合方案"
```

这个请求背后需要同时做：
- 查客户风险等级和持仓
- 研究适合的权益类产品（基金筛选）
- 研究适合的固收类产品（债券/货币基金）
- 分析当前市场环境
- 合规审查所有候选产品
- 汇总生成完整组合建议

如果一个 Agent 串行做完这些，响应会很慢，而且上下文越来越长，大模型容易混乱。

**解决办法：一个 Supervisor（协调者）+ 多个专职 Worker（执行者）。**

---

## 二、Supervisor 模式是什么

用一句话解释：**Supervisor 是包工头，Worker 是工人。**

```
你 → Supervisor（包工头）
         │
         ├──→ Worker A：研究权益产品  ──→ 返回结果
         ├──→ Worker B：研究固收产品  ──→ 返回结果    （三个并行）
         └──→ Worker C：分析市场环境  ──→ 返回结果
         │
         ↓（汇总三份结果）
         合规检查
         │
         ↓
         生成最终建议
         │
你 ← 完整投资组合方案
```

**分工原则：**
- Supervisor：只负责分配任务、汇总结果、做最终决策，不直接查数据
- Worker：只负责一件具体的事，不知道其他 Worker 在做什么，不能再派发子任务

---

## 三、LangGraph 的 Supervisor 实现方式

LangGraph 提供两种多 Agent 方式：

### 方式 A：LLM 驱动的 Supervisor（大模型决定派谁）

Supervisor 本身调一次大模型，让大模型决定下一步派哪个 Worker，或者是否可以汇总了。

适合：任务边界模糊、需要大模型判断的场景。

### 方式 B：Send API 并行派发（代码直接控制）

Supervisor 节点直接用代码决定并行启动哪些 Worker，不经过大模型。

适合：任务边界清晰、能提前确定需要哪些 Worker 的场景。

**对于投顾场景，推荐方式 B**：收到投资组合请求时，哪几类研究需要做是确定的，不需要大模型来决定。这样更快、更可控、合规也更容易保证。

---

## 四、投顾场景的多 Agent 设计

### 4.1 角色定义

| 角色 | 职责 | 使用的工具 |
|------|------|-----------|
| `supervisor` | 接收请求，并行派发三个 Worker，收集结果后交合规节点 | 无（纯协调） |
| `equity_researcher` | 筛选适合的权益类基金（股票型/混合型） | `query_product_info`, `query_fund_nav`, `search_product_prospectus` |
| `fixed_income_researcher` | 筛选适合的固收产品（债券/货币基金） | `query_product_info`, `query_fund_nav` |
| `market_analyzer` | 分析当前市场环境，判断入场时机和仓位建议 | `query_market_data`, `search_investment_knowledge` |
| `compliance_gate` | 对汇总后的候选产品做合规检查（沿用 03 里的设计） | `check_product_suitability`, `check_position_limit`, `check_special_restrictions` |
| `portfolio_builder` | 把合规通过的产品组合成完整方案，附风险提示 | `generate_risk_warning`, `calculate_portfolio_risk` |

### 4.2 完整流程图

```
用户请求："50万，帮我做投资组合"
    │
    ▼
[supervisor 节点]
  解析请求，用 Send API 并行派发三个 Worker
    │
    ├──→ [equity_researcher]   查权益产品  ──┐
    ├──→ [fixed_income_researcher] 查固收  ──┤  并行执行
    └──→ [market_analyzer]    分析市场     ──┘
                                              │
                                              ▼
                                      [aggregate 节点]
                                      收集三个 Worker 的结果
                                      合并候选产品列表
                                              │
                                              ▼
                                      [compliance_gate 节点]
                                      对所有候选产品做合规检查
                                      （复用 03 里的合规节点逻辑）
                                              │
                                              ▼
                                      [portfolio_builder 节点]
                                      大模型生成完整组合方案
                                      附加合规风险提示
                                              │
                                              ▼
                                      [audit_logging 节点]
                                              │
                                              ▼
                                            END
```

---

## 五、代码实现

```python
# src/domains/agent/multi_agent_graph.py

import asyncio
import json
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from .tools import (
    query_product_info,
    query_fund_nav,
    query_market_data,
    query_client_risk_profile,
    search_product_prospectus,
    search_investment_knowledge,
    check_product_suitability,
    check_position_limit,
    check_special_restrictions,
    calculate_portfolio_risk,
    generate_risk_warning,
)


llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)


# ──────────────────────────────────────────────────────────────
# Supervisor 节点
# 解析请求，决定派发哪些 Worker（这里用代码直接控制，不用大模型）
# ──────────────────────────────────────────────────────────────
def supervisor_node(state):
    """
    解析用户请求，并行派发研究任务。
    用 Send API 把任务分配给三个 Worker，它们会并行执行。
    """
    client_id = state["client_id"]
    user_request = state["user_request"]

    # 先查客户风险等级，这是所有后续工作的前提
    risk_info = query_client_risk_profile.invoke({"client_id": client_id})

    # 把公共上下文放进 state，Worker 们都能用
    base_context = {
        "client_id": client_id,
        "client_risk_level": risk_info["risk_level"],
        "user_request": user_request,
        "worker_results": [],   # 用于收集 Worker 返回的结果
        "audit_log": state.get("audit_log", []) + [{
            "step": "supervisor",
            "risk_level": risk_info["risk_level"],
            "time": datetime.utcnow().isoformat(),
        }],
    }

    # 用 Send 并行派发三个 Worker
    # 每个 Send 相当于：往指定节点发一条消息，独立执行
    return [
        Send("equity_researcher", {**base_context, "task": "equity"}),
        Send("fixed_income_researcher", {**base_context, "task": "fixed_income"}),
        Send("market_analyzer", {**base_context, "task": "market"}),
    ]


# ──────────────────────────────────────────────────────────────
# Worker：权益类产品研究
# ──────────────────────────────────────────────────────────────
async def equity_researcher_node(state):
    """
    专职研究权益类产品（股票型/混合型基金）。
    只做这一件事，不管其他 Worker 在做什么。
    """
    risk_level = state["client_risk_level"]
    user_request = state["user_request"]

    # 让大模型根据风险等级和请求，决定具体查哪些权益产品
    prompt = f"""
你是一个专职研究权益类基金的分析师。

客户风险等级：{risk_level}
客户需求：{user_request}

请推荐 2-3 只适合该客户风险等级的权益类基金（股票型或混合型）。
只关注权益类，固收类产品由其他人负责。
返回格式：{{"products": ["代码1", "代码2"], "rationale": "选择理由"}}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"products": [], "rationale": "解析失败"}

    # 补充查一下净值
    products_with_detail = []
    for code in result.get("products", []):
        nav = query_fund_nav.invoke({"fund_code": code})
        products_with_detail.append({"code": code, "nav": nav["nav"]})

    return {
        "worker_results": [{
            "type": "equity",
            "products": products_with_detail,
            "rationale": result.get("rationale", ""),
        }]
    }


# ──────────────────────────────────────────────────────────────
# Worker：固收类产品研究
# ──────────────────────────────────────────────────────────────
async def fixed_income_researcher_node(state):
    """
    专职研究固收类产品（债券型基金、货币基金）。
    """
    risk_level = state["client_risk_level"]
    user_request = state["user_request"]

    prompt = f"""
你是一个专职研究固收类产品的分析师。

客户风险等级：{risk_level}
客户需求：{user_request}

请推荐 2-3 只适合该客户的固收类产品（债券型基金或货币基金）。
只关注固收类，权益类由其他人负责。
返回格式：{{"products": ["代码1", "代码2"], "rationale": "选择理由"}}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"products": [], "rationale": "解析失败"}

    products_with_detail = []
    for code in result.get("products", []):
        nav = query_fund_nav.invoke({"fund_code": code})
        products_with_detail.append({"code": code, "nav": nav["nav"]})

    return {
        "worker_results": [{
            "type": "fixed_income",
            "products": products_with_detail,
            "rationale": result.get("rationale", ""),
        }]
    }


# ──────────────────────────────────────────────────────────────
# Worker：市场环境分析
# ──────────────────────────────────────────────────────────────
async def market_analyzer_node(state):
    """
    专职分析当前市场环境，给出仓位建议和入场时机判断。
    """
    # 查主要市场指数
    market_data = query_market_data.invoke({
        "index_codes": ["000001", "399001", "000300"],
        "period": "3m",
    })

    prompt = f"""
你是一个专职做市场分析的分析师。

当前市场数据：
{json.dumps(market_data, ensure_ascii=False, indent=2)}

请分析当前市场环境，给出：
1. 当前市场整体判断（偏强/震荡/偏弱）
2. 权益类资产建议仓位（百分比）
3. 当前是否适合建仓，以及理由

返回格式：{{"market_view": "...", "equity_position": 50, "timing": "适合/不适合", "reason": "..."}}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {"market_view": "震荡", "equity_position": 50, "timing": "适合", "reason": "解析失败"}

    return {
        "worker_results": [{
            "type": "market",
            "analysis": result,
        }]
    }


# ──────────────────────────────────────────────────────────────
# 汇总节点：收集所有 Worker 的结果
# ──────────────────────────────────────────────────────────────
def aggregate_node(state):
    """
    等三个 Worker 都执行完后，汇总它们的结果。
    LangGraph 会自动等所有并行 Worker 完成后才执行这个节点。
    """
    worker_results = state.get("worker_results", [])

    equity_result = next((r for r in worker_results if r["type"] == "equity"), {})
    fixed_income_result = next((r for r in worker_results if r["type"] == "fixed_income"), {})
    market_result = next((r for r in worker_results if r["type"] == "market"), {})

    # 合并所有候选产品
    all_candidates = (
        [p["code"] for p in equity_result.get("products", [])]
        + [p["code"] for p in fixed_income_result.get("products", [])]
    )

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "aggregate",
        "equity_candidates": [p["code"] for p in equity_result.get("products", [])],
        "fixed_income_candidates": [p["code"] for p in fixed_income_result.get("products", [])],
        "market_view": market_result.get("analysis", {}).get("market_view"),
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "candidate_products": all_candidates,
        "equity_research": equity_result,
        "fixed_income_research": fixed_income_result,
        "market_analysis": market_result,
        "audit_log": new_log,
    }


# ──────────────────────────────────────────────────────────────
# 合规检查节点（复用单 Agent 版本的逻辑）
# ──────────────────────────────────────────────────────────────
def compliance_gate_node(state):
    """合规强制关口，对所有候选产品逐一检查。"""
    client_id = state["client_id"]
    candidates = state.get("candidate_products") or []

    approved = []
    rejected = []
    compliance_results = {}

    for product_code in candidates:
        suitability = check_product_suitability.invoke({
            "client_id": client_id,
            "product_code": product_code,
        })
        position = check_position_limit.invoke({
            "client_id": client_id,
            "product_code": product_code,
            "purchase_amount": 10000.0,
        })
        restrictions = check_special_restrictions.invoke({
            "client_id": client_id,
            "product_code": product_code,
        })

        passed = (
            suitability["is_suitable"]
            and position["is_within_limit"]
            and not restrictions["has_restrictions"]
        )

        compliance_results[product_code] = {"passed": passed, "suitability": suitability}

        if passed:
            approved.append(product_code)
        else:
            rejected.append(product_code)

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "compliance_gate",
        "approved": approved,
        "rejected": rejected,
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "approved_products": approved,
        "rejected_products": rejected,
        "compliance_results": compliance_results,
        "audit_log": new_log,
    }


# ──────────────────────────────────────────────────────────────
# 组合构建节点：汇总所有研究成果，生成最终方案
# ──────────────────────────────────────────────────────────────
async def portfolio_builder_node(state):
    """
    把研究成果、市场分析、合规通过的产品整合成完整的投资组合方案。
    """
    approved = state.get("approved_products") or []
    risk_level = state.get("client_risk_level", "C3")
    market_analysis = state.get("market_analysis", {}).get("analysis", {})
    equity_research = state.get("equity_research", {})
    fixed_income_research = state.get("fixed_income_research", {})

    if not approved:
        return {
            "final_response": "很抱歉，经过合规审查，目前没有找到完全符合您风险等级的产品组合。建议预约理财经理进行人工咨询。",
            "audit_log": state.get("audit_log", []) + [{"step": "portfolio_builder", "result": "rejected_all"}],
        }

    # 风险等级映射
    risk_map = {"C1": "R1", "C2": "R2", "C3": "R3", "C4": "R4", "C5": "R5"}
    product_risk = risk_map.get(risk_level, "R3")
    risk_warning = generate_risk_warning.invoke({"product_risk_level": product_risk})

    prompt = f"""
你是一名专业的投资组合构建师，请根据以下研究成果生成完整的投资组合建议。

客户风险等级：{risk_level}
市场环境判断：{json.dumps(market_analysis, ensure_ascii=False)}
权益类研究结论：{json.dumps(equity_research, ensure_ascii=False)}
固收类研究结论：{json.dumps(fixed_income_research, ensure_ascii=False)}
通过合规审查的产品：{approved}

请生成：
1. 资产配置比例（权益/固收/货币各占多少）
2. 具体产品及建议配置比例（只能使用合规通过的产品）
3. 推荐理由（结合市场环境和客户风险等级）
4. 预期收益区间和主要风险提示

最后必须一字不改地附上：
【风险提示】{risk_warning}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "portfolio_builder",
        "approved_count": len(approved),
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "final_response": response.content,
        "audit_log": new_log,
    }


# ──────────────────────────────────────────────────────────────
# 审计日志节点
# ──────────────────────────────────────────────────────────────
async def audit_logging_node(state):
    record = {
        "conversation_id": state.get("conversation_id"),
        "client_id": state["client_id"],
        "approved": state.get("approved_products"),
        "rejected": state.get("rejected_products"),
        "steps": state.get("audit_log", []),
        "timestamp": datetime.utcnow().isoformat(),
    }
    # await save_to_mysql(record)
    print(f"[AUDIT] {json.dumps(record, ensure_ascii=False)}")
    return {}


# ──────────────────────────────────────────────────────────────
# 构建图
# ──────────────────────────────────────────────────────────────
def build_multi_agent_graph():
    builder = StateGraph(dict)

    # 注册所有节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("equity_researcher", equity_researcher_node)
    builder.add_node("fixed_income_researcher", fixed_income_researcher_node)
    builder.add_node("market_analyzer", market_analyzer_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("compliance_gate", compliance_gate_node)
    builder.add_node("portfolio_builder", portfolio_builder_node)
    builder.add_node("audit_logging", audit_logging_node)

    # supervisor 用 Send 并行派发三个 Worker（Send 的返回值就是边）
    builder.set_entry_point("supervisor")
    builder.add_conditional_edges("supervisor", lambda s: s, {})  # Send 会自动处理路由

    # 三个 Worker 完成后都汇聚到 aggregate
    builder.add_edge("equity_researcher", "aggregate")
    builder.add_edge("fixed_income_researcher", "aggregate")
    builder.add_edge("market_analyzer", "aggregate")

    # 后续流程
    builder.add_edge("aggregate", "compliance_gate")
    builder.add_edge("compliance_gate", "portfolio_builder")
    builder.add_edge("portfolio_builder", "audit_logging")
    builder.add_edge("audit_logging", END)

    return builder.compile()


multi_agent_graph = build_multi_agent_graph()
```

---

## 六、关键设计决策

### 6.1 Worker 不能再派发子任务

Worker 节点只能调工具，不能再调用其他 Agent。
否则会无限嵌套，失控。

具体做法：Worker 节点不持有 `Send`，也不持有其他子图的引用。
工具清单里也没有能派发任务的能力。

### 6.2 Worker 结果的合并方式

LangGraph 对并行 Worker 的结果合并有一个规则：**同名 key 会被追加（append），不会覆盖。**

所以三个 Worker 都返回 `{"worker_results": [...]}` 时，最终 state 里的 `worker_results` 是三个列表合并后的结果。这是 LangGraph Send API 的内置行为，不需要额外处理。

```python
# Worker A 返回：{"worker_results": [{"type": "equity", ...}]}
# Worker B 返回：{"worker_results": [{"type": "fixed_income", ...}]}
# Worker C 返回：{"worker_results": [{"type": "market", ...}]}
# aggregate 节点收到的 state["worker_results"] 是三者合并后的列表
```

要让 LangGraph 知道 `worker_results` 需要合并（而不是覆盖），在图初始化时指定：

```python
import operator
from langgraph.graph import StateGraph

# 告诉 LangGraph：worker_results 这个 key 用 list 追加方式合并
builder = StateGraph(dict, input={"worker_results": (list, operator.add)})
```

### 6.3 Supervisor 自己不调大模型

本设计里 Supervisor 是纯代码节点，直接决定派哪些 Worker，不经过大模型。

**好处：**
- 速度更快（少一次 API 调用）
- 行为确定，不依赖大模型决策
- 合规更容易保证（知道每次一定会执行合规检查）

**替代方案（LLM 驱动的 Supervisor）：**

如果场景更复杂、无法提前确定需要哪些 Worker，可以让大模型决定：

```python
async def llm_supervisor_node(state):
    """让大模型决定下一步派谁（更灵活但不确定性更高）"""
    worker_options = ["equity_researcher", "fixed_income_researcher", "market_analyzer", "FINISH"]

    prompt = f"""
用户请求：{state['user_request']}
已完成的工作：{[r['type'] for r in state.get('worker_results', [])]}

下一步应该调用哪个 Worker？从以下选项选一个：{worker_options}
如果所有需要的信息已经收集完毕，选 FINISH。
只返回 Worker 名称，不要其他内容。
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    next_worker = response.content.strip()

    if next_worker == "FINISH":
        return {"next": END}
    return {"next": next_worker}
```

---

## 七、单 Agent vs 多 Agent 怎么选

| 场景 | 用哪个 | 原因 |
|------|--------|------|
| 查单个产品净值 | 单 Agent（03 里的设计） | 一个工具调用，没必要多 Agent |
| 推荐 1-2 个产品 | 单 Agent | 复杂度不够，多 Agent 反而慢 |
| 生成完整投资组合 | **多 Agent**（本文档） | 需要并行研究多个维度 |
| 市场分析 + 产品推荐 + 组合优化 | **多 Agent** | 三类任务专业性不同，适合专职 Worker |
| 客户问"什么是ETF" | 单 Agent（RAG 查知识库） | 知识查询，不需要多 Worker |

---

## 八、与现有 Starlette 后端集成

视图层和 03 里的单 Agent 保持一致，只是换一个 graph：

```python
# src/domains/agent/views.py

from .graph import investment_graph            # 简单请求用这个
from .multi_agent_graph import multi_agent_graph   # 复杂请求用这个

@requires("authenticated")
async def agent_stream_view(request):
    body = await request.json()
    request_type = body.get("type", "simple")  # 前端传 simple/portfolio

    graph = multi_agent_graph if request_type == "portfolio" else investment_graph

    # 后续流程和 03 完全一样
    ...
```

---

## 九、执行时序图

```
时间线：

t=0   supervisor 执行，派发三个 Worker
      │
t=0+  ├── equity_researcher    开始（异步）
      ├── fixed_income_researcher 开始（异步）
      └── market_analyzer       开始（异步）
      │
      │   三个并行执行，各自调工具和大模型
      │
t=3s  equity_researcher    完成，返回结果
t=4s  market_analyzer       完成，返回结果
t=5s  fixed_income_researcher 完成，返回结果
      │
t=5s  aggregate 节点执行（等所有 Worker 完成后才执行）
      │
t=5s  compliance_gate 执行（串行，不能并发）
      │
t=6s  portfolio_builder 执行（大模型生成最终方案）
      │
t=8s  返回给用户

对比单 Agent 串行：约 12-15s
多 Agent 并行：约 8s（节省了并行部分的等待时间）
```
