# 第四课：Callback — 像中间件一样监控 Agent 的每一步

> LangGraph 节点控制"业务流程"，Callback 控制"横切关注点"。
> 两者分工明确，就像 Starlette 中路由逻辑和中间件的关系。

---

## 你已经知道的：Starlette 中间件

你的 Starlette 项目里，JWT 认证是中间件：

```python
# src/middleware/guards.py
class JWTAuthBackend(AuthenticationBackend):
    async def authenticate(self, request):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        # 解析 token，把用户信息填进 request
        ...
```

中间件不关心你的业务逻辑是什么，它只是在每个请求进来时"插一脚"：
- 记录日志
- 验证身份
- 计时
- ...

**LangChain/LangGraph 的 Callback 做的是同一件事：在 Agent 执行的每个关键事件上"插一脚"。**

---

## Callback 能监听什么事件

```python
from langchain_core.callbacks import AsyncCallbackHandler

class MyCallback(AsyncCallbackHandler):
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        """LLM 开始生成之前"""
        ...
    
    async def on_llm_end(self, response, **kwargs):
        """LLM 生成完成之后"""
        ...
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """工具开始执行之前"""
        ...
    
    async def on_tool_end(self, output, **kwargs):
        """工具执行完成之后"""
        ...
    
    async def on_tool_error(self, error, **kwargs):
        """工具执行出错时"""
        ...
    
    async def on_chain_start(self, serialized, inputs, **kwargs):
        """LangGraph 节点（链）开始执行"""
        ...
    
    async def on_chain_end(self, outputs, **kwargs):
        """LangGraph 节点（链）执行完成"""
        ...
```

---

## 类比：中间件 vs Callback

| Starlette 中间件 | LangChain Callback |
|-----------------|-------------------|
| `async def __call__(self, scope, receive, send)` | `async def on_llm_start(...)` 等 |
| 每个 HTTP 请求都会触发 | 每次 LLM 调用/工具调用都会触发 |
| 注册到 app：`app.add_middleware(...)` | 注册到 invoke：`config={"callbacks": [...]}` |
| 可以读 request，也可以修改 response | 只能读，不能干预 Agent 行为 |
| 适合：认证、日志、CORS | 适合：审计、计时、合规监控 |

**关键区别：Callback 是只读的观察者，不能改变 Agent 的执行路径。**
（改变路径是 LangGraph 条件边的工作。）

---

## 投顾场景的审计 Callback

```python
# src/domains/agent/callbacks.py

import time
from datetime import datetime
from langchain_core.callbacks import AsyncCallbackHandler


class FinancialAuditCallback(AsyncCallbackHandler):
    """
    金融合规审计 Callback。
    
    职责：
    1. 记录每次 LLM 调用的耗时
    2. 记录每次工具调用（尤其是合规工具）
    3. 检测大模型是否绕过合规工具直接给出投资建议
    
    类比：这是你 Starlette 项目里的"审计中间件"，
    只不过它监控的不是 HTTP 请求，而是 Agent 的每一步。
    """

    def __init__(self, conversation_id, advisor_id, client_id):
        self.conversation_id = conversation_id
        self.advisor_id = advisor_id
        self.client_id = client_id
        self.records = []           # 所有事件记录
        self._llm_start_time = None

    # ── LLM 调用监控 ──────────────────────────────────────────

    async def on_llm_start(self, serialized, prompts, **kwargs):
        self._llm_start_time = time.time()

    async def on_llm_end(self, response, **kwargs):
        duration = time.time() - (self._llm_start_time or 0)
        
        # 提取 LLM 输出的文字
        content = ""
        if response.generations:
            content = response.generations[0][0].text
        
        # 检测 LLM 是否直接给出投资建议（未经合规工具就推荐）
        # 这些关键词表明 LLM 在"越权"直接推荐
        ALERT_KEYWORDS = ["推荐买入", "建议申购", "建议加仓", "立即购买", "马上买"]
        has_alert = any(kw in content for kw in ALERT_KEYWORDS)
        
        self.records.append({
            "event": "llm_end",
            "duration_s": round(duration, 2),
            "direct_advice_alert": has_alert,
            "time": datetime.utcnow().isoformat(),
        })
        
        if has_alert:
            # 实际环境里发告警（邮件/钉钉/Slack）
            print(f"[COMPLIANCE ALERT] LLM 直接给出投资建议，对话 {self.conversation_id} 需要人工复查")

    # ── 工具调用监控 ──────────────────────────────────────────

    async def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "unknown")
        
        self.records.append({
            "event": "tool_call",
            "tool": tool_name,
            "input": input_str[:300],   # 截断，防止太长
            # check_ 开头的工具是合规工具，特别标记
            "is_compliance_tool": tool_name.startswith("check_"),
            "time": datetime.utcnow().isoformat(),
        })

    async def on_tool_end(self, output, **kwargs):
        # 找到最近一条 tool_call 记录，补充输出
        for record in reversed(self.records):
            if record["event"] == "tool_call" and "output" not in record:
                record["output"] = str(output)[:300]
                record["success"] = True
                break

    async def on_tool_error(self, error, **kwargs):
        for record in reversed(self.records):
            if record["event"] == "tool_call" and "output" not in record:
                record["success"] = False
                record["error"] = str(error)
                break

    # ── 合规违规检测 ──────────────────────────────────────────

    def has_compliance_violation(self):
        """
        判断是否存在合规违规：
        LLM 给出了投资建议，但整个对话过程中没有调用过合规检查工具。
        
        这说明大模型绕过了合规流程，直接输出推荐——这在银行场景下是违规的。
        """
        had_compliance_check = any(
            r["event"] == "tool_call" and r.get("is_compliance_tool")
            for r in self.records
        )
        had_direct_advice = any(
            r["event"] == "llm_end" and r.get("direct_advice_alert")
            for r in self.records
        )
        return had_direct_advice and not had_compliance_check

    def get_summary(self):
        """生成本次对话的审计摘要"""
        total_llm_time = sum(
            r["duration_s"] for r in self.records if r["event"] == "llm_end"
        )
        tool_calls = [r for r in self.records if r["event"] == "tool_call"]
        
        return {
            "conversation_id": self.conversation_id,
            "total_llm_duration_s": round(total_llm_time, 2),
            "tool_call_count": len(tool_calls),
            "compliance_tools_called": [
                r["tool"] for r in tool_calls if r.get("is_compliance_tool")
            ],
            "has_violation": self.has_compliance_violation(),
        }
```

---

## 在 Starlette 视图里使用 Callback

```python
# src/domains/agent/views.py

import uuid, json
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

    # 实例化 Callback（每个请求一个实例，不能复用！）
    audit_cb = FinancialAuditCallback(
        conversation_id=conversation_id,
        advisor_id=request.user.user_id,
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
                # 把 Callback 传给图，LangGraph 会在每个事件触发时调用它
                config={"callbacks": [audit_cb]},
                stream_mode="values",
            ):
                if chunk.get("final_response"):
                    data = json.dumps(
                        {"content": chunk["final_response"]},
                        ensure_ascii=False,
                    )
                    yield f"data: {data}\n\n"

            # 图执行完成后，检查有没有合规违规
            if audit_cb.has_compliance_violation():
                # 发告警
                summary = audit_cb.get_summary()
                print(f"[VIOLATION] {json.dumps(summary, ensure_ascii=False)}")

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## 一个常见误解：Callback 能不能"阻止"某些行为

**不能。** Callback 是观察者，不是守门员。

```python
async def on_tool_start(self, serialized, input_str, **kwargs):
    # ❌ 你没有办法在这里抛异常来阻止工具执行
    # ❌ 你没有办法在这里修改工具参数
    # ✅ 你只能记录、告警、统计
    ...
```

如果你需要"阻止"某个操作，那是 LangGraph 节点和条件边的工作，不是 Callback 的工作。

**分工总结：**
- **LangGraph 节点/条件边**：控制流程走向（合规检查通过才能推荐）
- **Callback**：透明监控（记录谁做了什么，告警异常情况）

---

## Callback 的另一个用途：性能监控

```python
class PerformanceCallback(AsyncCallbackHandler):
    """记录每个节点和 LLM 调用的耗时，用于性能优化"""
    
    def __init__(self):
        self.timings = []
        self._start_times = {}
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        run_id = kwargs.get("run_id")
        self._start_times[str(run_id)] = time.time()
    
    async def on_llm_end(self, response, **kwargs):
        run_id = str(kwargs.get("run_id"))
        start = self._start_times.pop(run_id, time.time())
        self.timings.append({
            "type": "llm",
            "duration_ms": round((time.time() - start) * 1000),
        })
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id"))
        self._start_times[run_id] = time.time()
        
    async def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id"))
        start = self._start_times.pop(run_id, time.time())
        self.timings.append({
            "type": "tool",
            "duration_ms": round((time.time() - start) * 1000),
        })
    
    def report(self):
        total = sum(t["duration_ms"] for t in self.timings)
        print(f"总耗时: {total}ms")
        for t in self.timings:
            print(f"  {t['type']}: {t['duration_ms']}ms")
```

---

## 小结

```
Callback 的定位：
  - 不控制流程（那是 LangGraph 图结构的工作）
  - 只观察事件（LLM 调用、工具调用）

使用方式：
  - 继承 AsyncCallbackHandler
  - 实现 on_llm_start/on_llm_end/on_tool_start/on_tool_end 等方法
  - 在 graph.ainvoke/astream 时传入 config={"callbacks": [cb]}

投顾场景的两个核心用途：
  1. 合规审计：检测 LLM 是否绕过合规工具直接推荐
  2. 审计日志：记录每次对话的完整工具调用链路
```

下一课：[05 - 多 Agent 并发：让三个专家同时工作](./05-multi-agent-concurrency.md)
