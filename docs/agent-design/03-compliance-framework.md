# 合规审计与风险控制框架

> 金融 Agent 与普通 Chatbot 最大的区别：普通 Chatbot 的错误只是信息错误，
> 金融 Agent 的错误可能违反监管法规。

---

## 一、为什么合规不能靠 Prompt

新手最直觉的方法：在 System Prompt 里写"你必须先检查客户风险等级"。

**这不够，原因有三：**

1. **大模型不可靠**：可能"忘记"遵守，无法 100% 保证
2. **无法审计**：Prompt 约束无法产生可被监管追踪的记录
3. **可被绕过**：换一种提问方式可能让大模型绕过 Prompt 限制

**正确做法：把合规逻辑编码进 LangGraph 的图结构，让它成为不可绕过的节点。**

---

## 二、合规图结构设计

### 2.1 完整流程图

```
用户输入："帮我给客户 C001 推荐一个适合他的基金"
    │
    ▼
[节点1] info_gathering：并行收集信息
  ├── query_client_risk_profile(client_id)   ← 查风险等级
  ├── query_client_holdings(client_id)       ← 查当前持仓
  └── query_market_data([...])               ← 查当前市场行情
  大模型不参与，直接调工具
    │
    ▼
[节点2] llm_recommend：大模型生成候选产品（草稿）
  大模型根据收集的信息，结合知识，生成 2-3 个候选产品代码
  注意：这里的输出还不是最终建议，必须过合规
    │
    ▼
[节点3] compliance_gate：合规强制关口（核心）
  对每个候选产品，串行执行三项检查：
  ├── check_product_suitability()   ← 适当性检查
  ├── check_position_limit()        ← 仓位限制
  └── check_special_restrictions()  ← 特殊限制
  大模型不参与，纯规则执行
    │
    ├── [有通过的产品]
    │       ↓
    │   [节点4a] generate_recommendation
    │   生成最终推荐文字 + 附加合规风险提示（generate_risk_warning）
    │
    └── [全部不通过]
            ↓
        [节点4b] generate_rejection
        向客户说明原因，建议降级替代产品
    │
    ▼（所有路径汇聚）
[节点5] audit_logging：审计日志持久化（必须经过）
  记录：请求、收集的信息、合规检查结果、最终输出
  写入 MySQL audit_logs 表
  不论成功/拒绝，都要记录
    │
    ▼
  END（返回给用户）
```

### 2.2 LangGraph 代码实现

```python
# src/domains/agent/graph.py

import asyncio
import json
import re
import uuid
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from .tools import (
    query_client_risk_profile,
    query_client_holdings,
    check_product_suitability,
    check_position_limit,
    check_special_restrictions,
    generate_risk_warning,
    ALL_TOOLS,
)


# ── LLM 初始化 ────────────────────────────────────────────────
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
llm_for_candidate = llm  # 生成候选时不给工具（防止它自己跑去调工具）

SYSTEM_PROMPT = """你是一名专业的银行投资顾问助手。规则：
1. 在推荐任何产品前，必须先了解客户风险承受能力等级
2. 不得向客户推荐风险等级超出其承受能力的产品
3. 所有建议必须附带合规风险提示
"""


# ── 节点实现 ──────────────────────────────────────────────────
async def info_gathering_node(state):
    """并行收集客户信息，不需要大模型参与"""
    client_id = state["client_id"]

    risk_result, holdings_result = await asyncio.gather(
        asyncio.to_thread(query_client_risk_profile.invoke, {"client_id": client_id}),
        asyncio.to_thread(query_client_holdings.invoke, {"client_id": client_id}),
    )

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "info_gathering",
        "risk_level": risk_result["risk_level"],
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "client_risk_level": risk_result["risk_level"],
        "risk_is_expired": risk_result["is_expired"],
        "client_holdings": holdings_result["holdings"],
        "audit_log": new_log,
    }


async def llm_recommend_node(state):
    """大模型根据收集的信息生成候选产品代码列表"""
    context = f"""
客户信息：
- 客户 ID：{state['client_id']}
- 风险等级：{state['client_risk_level']}
- 风险评测是否过期：{state.get('risk_is_expired', False)}
- 当前持仓数量：{len(state.get('client_holdings') or [])} 只

请根据以上信息，推荐 2-3 个适合该客户的基金产品代码。
只返回产品代码的 JSON 数组，不要其他内容。示例格式：["000001", "110011", "519066"]
"""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"],
        HumanMessage(content=context),
    ]
    response = await llm_for_candidate.ainvoke(messages)

    # 从大模型回复中提取产品代码列表
    codes_match = re.search(r'\[.*?\]', response.content)
    candidates = json.loads(codes_match.group()) if codes_match else []

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "llm_recommend",
        "candidates": candidates,
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "candidate_products": candidates,
        "messages": state["messages"] + [response],
        "audit_log": new_log,
    }


async def compliance_gate_node(state):
    """合规检查节点：三项检查全部串行，不能并发"""
    client_id = state["client_id"]
    candidates = state.get("candidate_products") or []

    compliance_results = {}
    approved = []
    rejected = []

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

        all_passed = (
            suitability["is_suitable"]
            and position["is_within_limit"]
            and not restrictions["has_restrictions"]
        )

        compliance_results[product_code] = {
            "passed": all_passed,
            "suitability": suitability,
            "position": position,
            "restrictions": restrictions,
        }

        if all_passed:
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
        "compliance_results": compliance_results,
        "approved_products": approved,
        "rejected_products": rejected,
        "audit_log": new_log,
    }


async def generate_recommendation_node(state):
    """生成最终推荐（有通过合规的产品时）"""
    approved = state["approved_products"]
    risk_level = state["client_risk_level"]

    # 风险等级映射
    risk_map = {"C1": "R1", "C2": "R2", "C3": "R3", "C4": "R4", "C5": "R5"}
    product_risk = risk_map.get(risk_level, "R3")

    # 获取合规风险提示（不能省略，不能改写）
    risk_warning = generate_risk_warning.invoke({"product_risk_level": product_risk})

    prompt = f"""
已通过合规审查的产品：{approved}
客户风险等级：{risk_level}

请用专业但易懂的语言，向客户介绍这些产品及推荐原因。
最后必须一字不改地附上以下风险提示：

【风险提示】{risk_warning}
"""
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "generate_recommendation",
        "approved_count": len(approved),
        "time": datetime.utcnow().isoformat(),
    })

    return {
        "final_response": response.content,
        "messages": state["messages"] + [response],
        "audit_log": new_log,
    }


async def generate_rejection_node(state):
    """生成拒绝响应（所有候选产品均未通过合规）"""
    reasons = []
    for code, result in state.get("compliance_results", {}).items():
        if not result["passed"] and not result["suitability"]["is_suitable"]:
            reasons.append(f"产品 {code} 风险等级超出您的承受范围")

    risk_label_map = {
        "C1": "保守型", "C2": "稳健型", "C3": "平衡型", "C4": "成长型", "C5": "激进型"
    }
    risk_label = risk_label_map.get(state["client_risk_level"], state["client_risk_level"])

    response_text = (
        f"非常抱歉，根据合规要求，建议的产品不适合您目前的风险等级（{risk_label}）：\n"
        + "\n".join(f"- {r}" for r in reasons)
        + "\n\n我可以为您推荐更符合您风险等级的替代产品，是否需要？"
    )

    new_log = list(state.get("audit_log", []))
    new_log.append({
        "step": "generate_rejection",
        "reasons": reasons,
        "time": datetime.utcnow().isoformat(),
    })

    return {"final_response": response_text, "audit_log": new_log}


async def audit_logging_node(state):
    """审计日志持久化，所有路径都必须经过"""
    record = {
        "conversation_id": state.get("conversation_id"),
        "client_id": state["client_id"],
        "timestamp": datetime.utcnow().isoformat(),
        "steps": state.get("audit_log", []),
        "approved": state.get("approved_products"),
        "rejected": state.get("rejected_products"),
        "compliance_passed": bool(state.get("approved_products")),
    }
    # 实际实现：await save_to_mysql(record)
    print(f"[AUDIT] {json.dumps(record, ensure_ascii=False)}")
    return {}


# ── 路由函数 ──────────────────────────────────────────────────
def route_after_compliance(state):
    if state.get("approved_products"):
        return "recommend"
    return "reject"


# ── 构建图 ────────────────────────────────────────────────────
def build_graph():
    builder = StateGraph(dict)

    builder.add_node("info_gathering", info_gathering_node)
    builder.add_node("llm_recommend", llm_recommend_node)
    builder.add_node("compliance_gate", compliance_gate_node)
    builder.add_node("generate_recommendation", generate_recommendation_node)
    builder.add_node("generate_rejection", generate_rejection_node)
    builder.add_node("audit_logging", audit_logging_node)

    builder.set_entry_point("info_gathering")
    builder.add_edge("info_gathering", "llm_recommend")
    builder.add_edge("llm_recommend", "compliance_gate")
    builder.add_conditional_edges(
        "compliance_gate",
        route_after_compliance,
        {"recommend": "generate_recommendation", "reject": "generate_rejection"},
    )
    builder.add_edge("generate_recommendation", "audit_logging")
    builder.add_edge("generate_rejection", "audit_logging")
    builder.add_edge("audit_logging", END)

    return builder.compile()


investment_graph = build_graph()
```

---

## 三、Callback：细粒度审计

LangGraph 节点负责流程级审计，Callback 负责 LLM 层的细粒度记录。

```python
# src/domains/agent/callbacks.py

import time
import uuid
from datetime import datetime
from langchain_core.callbacks import AsyncCallbackHandler


class FinancialAuditCallback(AsyncCallbackHandler):
    """
    细粒度审计 Callback：记录每次 LLM 调用和工具调用，
    并检测 LLM 是否绕过合规工具直接给出投资建议。
    """

    def __init__(self, conversation_id, advisor_id, client_id):
        self.conversation_id = conversation_id
        self.advisor_id = advisor_id
        self.client_id = client_id
        self.records = []
        self._llm_start_time = None

    async def on_llm_start(self, serialized, prompts, **kwargs):
        self._llm_start_time = time.time()

    async def on_llm_end(self, response, **kwargs):
        duration = time.time() - (self._llm_start_time or 0)
        content = response.generations[0][0].text if response.generations else ""

        # 检测 LLM 是否直接给出投资建议（合规风险：未调工具就推荐）
        ALERT_KEYWORDS = ["推荐买入", "建议申购", "建议加仓", "立即购买"]
        alert = any(kw in content for kw in ALERT_KEYWORDS)

        self.records.append({
            "event": "llm_end",
            "duration_s": round(duration, 2),
            "direct_advice_alert": alert,      # True 说明需要人工复查
            "conversation_id": self.conversation_id,
            "time": datetime.utcnow().isoformat(),
        })

    async def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "unknown")
        self.records.append({
            "event": "tool_call",
            "tool": tool_name,
            "input": input_str[:300],
            "is_compliance_tool": tool_name.startswith("check_"),
            "time": datetime.utcnow().isoformat(),
        })

    async def on_tool_end(self, output, **kwargs):
        if self.records and self.records[-1]["event"] == "tool_call":
            self.records[-1]["output"] = str(output)[:300]
            self.records[-1]["success"] = True

    async def on_tool_error(self, error, **kwargs):
        if self.records and self.records[-1]["event"] == "tool_call":
            self.records[-1]["success"] = False
            self.records[-1]["error"] = str(error)

    def has_compliance_violation(self):
        """检查是否存在合规违规：LLM 直接给建议但没有经过合规工具"""
        had_compliance_check = any(
            r["event"] == "tool_call" and r.get("is_compliance_tool")
            for r in self.records
        )
        had_direct_advice = any(
            r["event"] == "llm_end" and r.get("direct_advice_alert")
            for r in self.records
        )
        return had_direct_advice and not had_compliance_check

    async def save_to_db(self, db_session):
        audit_id = str(uuid.uuid4())
        # await db_session.execute(INSERT INTO llm_audit_events ...)
        return audit_id
```

---

## 四、与 Starlette 集成

### 4.1 新增路由

```python
# src/routes.py（在现有路由列表中追加）

from src.domains.agent.views import agent_stream_view

routes = [
    # ... 现有路由 ...
    Route("/api/v1/agent/stream", agent_stream_view, methods=["POST"]),
]
```

### 4.2 视图层

```python
# src/domains/agent/views.py

import uuid
import json
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.authentication import requires
from langchain_core.messages import HumanMessage

from src.core.response import fail
from src.core.codes import BizCode
from .graph import investment_graph
from .callbacks import FinancialAuditCallback


@requires("authenticated")
async def agent_stream_view(request):
    body = await request.json()
    user_input = body.get("message", "").strip()
    client_id = body.get("client_id", "").strip()

    if not client_id:
        return fail(BizCode.PARAM_MISSING)

    conversation_id = str(uuid.uuid4())
    advisor_id = request.user.user_id

    audit_cb = FinancialAuditCallback(
        conversation_id=conversation_id,
        advisor_id=advisor_id,
        client_id=client_id,
    )

    async def event_stream():
        try:
            async for chunk in investment_graph.astream(
                {
                    "messages": [HumanMessage(content=user_input)],
                    "client_id": client_id,
                    "conversation_id": conversation_id,
                    "audit_log": [],
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

            # 检查合规违规并告警
            if audit_cb.has_compliance_violation():
                # 发送告警通知（发邮件/写数据库/推送到监控系统）
                pass

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## 五、数据库表（新增到 docs/roles.sql）

```sql
-- 对话会话记录
CREATE TABLE agent_conversations (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    conv_id     VARCHAR(36) NOT NULL UNIQUE,
    advisor_id  BIGINT UNSIGNED NOT NULL,
    client_id   VARCHAR(64) NOT NULL,
    started_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at    DATETIME,
    INDEX idx_advisor_client (advisor_id, client_id)
);

-- 合规检查记录（监管报告核心，每次检查一行）
CREATE TABLE compliance_checks (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    check_id            VARCHAR(36) NOT NULL UNIQUE,
    conv_id             VARCHAR(36) NOT NULL,
    advisor_id          BIGINT UNSIGNED NOT NULL,
    client_id           VARCHAR(64) NOT NULL,
    product_code        VARCHAR(32) NOT NULL,
    client_risk_level   VARCHAR(10) NOT NULL,
    product_risk_level  VARCHAR(10) NOT NULL,
    suitability_passed  TINYINT(1) NOT NULL,
    position_passed     TINYINT(1) NOT NULL,
    restriction_passed  TINYINT(1) NOT NULL,
    overall_passed      TINYINT(1) NOT NULL,
    check_detail        JSON,
    checked_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conv (conv_id),
    INDEX idx_advisor_date (advisor_id, checked_at)
);

-- LLM 调用审计（细粒度，供事后分析）
CREATE TABLE llm_audit_events (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    conv_id                 VARCHAR(36) NOT NULL,
    event_type              VARCHAR(32) NOT NULL,
    tool_name               VARCHAR(64),
    is_compliance_tool      TINYINT(1) DEFAULT 0,
    direct_advice_alert     TINYINT(1) DEFAULT 0,   -- 1 表示需要人工复查
    duration_ms             INT,
    event_detail            JSON,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conv (conv_id),
    INDEX idx_alert (direct_advice_alert, created_at)
);
```

---

## 六、风险控制总结

| 风险类型 | 控制手段 | 代码位置 |
|---------|---------|---------|
| 适当性违规 | 合规节点强制执行，流程绕不过 | `compliance_gate_node` |
| 大模型绕过合规直接推荐 | Callback 检测 + 告警 | `has_compliance_violation()` |
| 仓位过度集中 | 仓位限制工具串行检查 | `check_position_limit` |
| 事后监管审查 | 完整合规检查记录 | `compliance_checks` 表 |
| 风险提示被省略 | 工具生成，禁止自行改写 | `generate_risk_warning` 的 docstring |
| 对话历史跨客户泄露 | 每个客户独立 thread_id | LangGraph Checkpointer |
