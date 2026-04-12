# Agent Chat 请求流转全解析

> 对应源码：`src/domains/agent/views.py` → `src/domains/agent/pipeline.py` → `src/domains/agent/nodes/`

---

## 一、全局流转概览

```
HTTP POST /agent.chat
       │
       ▼
  views.chat()          ← 解析请求、组装 state、启动后台任务
       │
       ├─── asyncio.create_task(run_pipeline_and_save())
       │           │
       │           ▼
       │     pipeline.run(state)    ← Pipeline 协调器，不含业务逻辑
       │           │
       │     Node1 意图识别  ──── LLM (JSON mode)
       │           │
       │     Node2 合规拦截 + Skill 路由  ──── 纯代码逻辑 / 风控引擎
       │           │
       │     Node3 Skill 执行 + RAG 检索  ──── 并发执行
       │           │
       │     Node4 响应合成  ──── LLM (流式 SSE)
       │           │
       │     Node5 审计写入  ──── 异步 DB（不阻塞响应）
       │
       └─── StreamingResponse(event_generator())   ← 即时返回给前端
```

**关键设计**：Pipeline 和 StreamingResponse **并发运行**。`views.chat()` 用
`asyncio.create_task()` 启动 Pipeline 后立刻返回 `StreamingResponse`，
前端通过 SSE 实时收到 Pipeline 推送的 token，流自然结束。

---

## 二、views.chat() 逐步拆解

```python
# Step 1：解析请求体
body = serial.from_json(await request.body())
message = (body.get('message') or '').strip()
session_id = body.get('session_id') or ''

# Step 2：加载或创建会话，取出历史消息
session, history = await service.load_or_create_session(user.user_id, session_id)
# 会话超时(4h) / 不存在 / 已关闭 → 自动创建新会话并清空 history

# Step 3：构建 AgentState（见下文详解）
state = make_initial_state(message=message, user=user, session=session, history=history)

# Step 4：创建 SSE 队列，挂载到 state（Pipeline 向此推送 token）
token_queue = asyncio.Queue()
state['_sse_queue'] = token_queue

# Step 5：把 Pipeline 丢进后台，不等它完成
asyncio.create_task(run_pipeline_and_save())
#   Pipeline 完成后自动调用 service.save_turn_messages() 持久化本轮对话

# Step 6：立刻返回 SSE 流
return StreamingResponse(event_generator(), media_type='text/event-stream', ...)
```

`event_generator()` 逻辑极简：循环从 `token_queue` 取事件，遇到 `None` 哨兵
就退出（哨兵由 Pipeline `finally` 块中的 `_signal_sse_done()` 写入）。

---

## 三、AgentState 字典完整注解

`state` 是整个 Pipeline 唯一的数据载体，贯穿所有节点。
结构分为 4 个顶级域 + 2 个运行时私有键：

```
state
├── input          ← 输入域（只读，节点禁止修改）
├── working        ← 工作域（节点依次填充）
├── audit          ← 审计域（只追加，不修改已有条目）
├── control        ← 控制域（流程信号）
├── _sse_queue     ← 运行时私有（SSE 队列，不落库）
└── _review_task_id← 运行时私有（人工审核时的任务 ID，不落库）
```

---

### 3.1 `input` — 输入域

> 由 `make_initial_state()` 一次性写入，此后 **只读**，任何节点不得修改。

| 键 | 类型 | 说明 |
|---|---|---|
| `session_id` | `str` | 当前会话 ID（`agent_session.session_id`），新会话由 service 创建 |
| `turn_id` | `str` | 本轮对话唯一 ID（`uuid4().hex`），用于关联消息和审计 |
| `run_id` | `str` | 请求级追踪 ID，从中间件注入的 `ContextVar` 取出，用于日志追踪 |
| `user.user_id` | `int/str` | 当前登录用户 ID |
| `user.username` | `str` | 用户名 |
| `user.roles` | `list[str]` | 用户角色列表，Node2 权限检查的依据 |
| `user.risk_clearance` | `str` | 风险许可等级（JWT 暂无，默认空字符串） |
| `user.department` | `str` | 所属部门（JWT 暂无，默认空字符串） |
| `message` | `str` | 用户本轮输入的原始文本 |
| `history` | `list[dict]` | 会话历史消息，格式 `[{"role": "user"/"assistant", "content": "..."}]`，最多 40 条 |
| `received_at` | `str` | 请求接收时间（ISO 8601 UTC），用于审计和耗时计算 |

---

### 3.2 `working` — 工作域

> 各节点的"黑板"，节点依次在此读/写，后节点依赖前节点的产出。

#### `working.intent` — Node1 填充

意图识别的 LLM 结构化输出。

| 键 | 类型 | 说明 |
|---|---|---|
| `category` | `str` | 意图类别，取值见下表 |
| `sub_intent` | `str` | 细分意图，如 `product_query` 下区分净值/收益率等 |
| `entities` | `dict` | 从用户输入提取的实体，含 `product_id`、`customer_id`、`amount` 等 |
| `confidence` | `float` | 置信度 `[0, 1]`，< 0.6 降级为 `ambiguous`，0.6~0.85 附带 `low_confidence_note` |
| `needs_clarification` | `bool` | `true` 时 Pipeline 在 Node1 后短路，返回澄清问题 |
| `clarification_question` | `str\|null` | 澄清问题文本 |
| `low_confidence_note` | `str` | 低置信度时的友好提示（如"已按[xxx]理解"） |
| `llm_raw_output` | `str` | LLM 原始输出字符串，供审计溯源 |

**意图类别枚举：**

| 值 | 含义 |
|---|---|
| `product_query` | 查询产品基本信息 |
| `product_compare` | 对比多个产品 |
| `portfolio_analysis` | 分析客户持仓 |
| `risk_assessment` | 风险评估/压力测试 |
| `redemption_initiate` | 发起赎回申请 |
| `audit_query` | 查询审计日志 |
| `small_talk` | 闲聊（→ 短路） |
| `out_of_scope` | 超出范围（→ 短路） |
| `ambiguous` | 意图不明确（→ 返回澄清） |

---

#### `working.route` — Node2 填充

合规检查结果 + Skill 路由决策。

| 键 | 类型 | 说明 |
|---|---|---|
| `selected_skills` | `list[dict]` | 本次需要执行的 Skill 列表，每项含 `skill_id`、`params`、`depends_on` |
| `compliance.passed` | `bool` | 合规是否通过，`false` 时 Pipeline 在 Node2 后短路 |
| `compliance.events` | `list` | 本次触发的合规事件（冗余备份，主记录在 `audit.compliance_events`） |
| `human_review.required` | `bool` | 是否需要人工审核 |
| `human_review.reason` | `str\|null` | 触发审核的原因描述 |
| `human_review.rule_id` | `str\|null` | 触发的审核规则 ID |
| `human_review.assign_to_role` | `str\|null` | 指派给哪个角色审核（如 `COMPLIANCE`、`RISK_OFFICER`） |
| `human_review.sla_hours` | `int\|null` | 承诺处理时限（小时） |

---

#### `working.skill_results` — Node3 填充

所有 Skill 执行结果的列表，每项结构：

| 键 | 类型 | 说明 |
|---|---|---|
| `skill_id` | `str` | Skill 标识符 |
| `status` | `str` | `ok` / `degraded`（超时但允许降级）/ `error` |
| `data` | `dict\|null` | Skill 返回的结构化数据，供 Node4 组装 prompt |
| `error_msg` | `str\|null` | 失败原因 |
| `duration_ms` | `int` | 执行耗时（毫秒） |
| `idempotency_key` | `str\|null` | 写操作专用幂等键（`turn_id:skill_id`），防重复提交 |

> **写操作关键失败判定**：若 `write_operation=true` 的 Skill 状态不为 `ok`，
> Pipeline 视为关键失败，整体返回 `failed`。读操作失败不触发此逻辑。

---

#### `working.knowledge_chunks` — Node3 填充

RAG 检索返回的知识库片段列表，每项含 `content` 字段，Node4 将其填入 prompt 的
`[知识库参考资料]` 区块（最多取前 3 条）。

---

#### `working.response` — Node4 填充（部分情况 Node1/Node2 提前填充）

最终要返回给用户的完整响应。

| 键 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 完整回复文本（SSE 流结束后才完整） |
| `validation.number_check_passed` | `bool` | 数值一致性校验是否通过（响应数值须与 skill_results 对齐） |
| `validation.content_filter_passed` | `bool` | 合规用语过滤是否通过（禁止"保证收益"等词） |
| `validation.violations` | `list[str]` | 命中的违禁正则列表 |
| `token_usage.prompt_tokens` | `int` | 本节点消耗的 prompt token 数 |
| `token_usage.completion_tokens` | `int` | 本节点消耗的 completion token 数 |

> Node1（意图不明确时）和 Node2（合规拦截时）也会提前写 `working.response`
> 并短路返回，此时 `validation` 字段为空占位 `{}`。

---

### 3.3 `audit` — 审计域

> 只追加，不修改已有条目。Node5 负责将此域写入 `agent_audit_log` 表。

#### `audit.node_traces`

记录每个节点的执行轨迹（每个节点调用 `append_node_trace()` 写入）：

| 键 | 说明 |
|---|---|
| `node` | 节点名称，如 `node1_intent_parser` |
| `started_at` | 节点开始时间（ISO 8601 UTC） |
| `ended_at` | 节点结束时间 |
| `duration_ms` | 执行耗时（毫秒） |
| `status` | `ok` / `failed` |
| `summary` | 节点自描述摘要，如"意图=product_query, 置信度=0.92" |

---

#### `audit.compliance_events`

合规检查触发的事件列表（每次 `append_compliance_event()` 追加）：

| 键 | 说明 |
|---|---|
| `event_type` | 事件类型：`permission_check` / `risk_level_check` / `rule_engine_check` / `content_compliance_check` |
| `result` | `passed` / `blocked` / `review_triggered` |
| `rule_id` | 对应规则 ID，如 `permission_matrix`、`risk_match_rule` |
| `detail` | 人类可读描述 |
| `at` | 事件发生时间（ISO 8601 UTC） |

---

#### `audit.llm_calls`

每次 LLM 调用的记录（Node1、Node4 各写一条）：

| 键 | 说明 |
|---|---|
| `node` | 调用方节点名称 |
| `model` | 模型名称 |
| `prompt_tokens` | 输入 token 数 |
| `completion_tokens` | 输出 token 数 |
| `duration_ms` | 调用耗时 |
| `at` | 调用时间 |

---

### 3.4 `control` — 控制域

Pipeline 流程控制信号，各节点读取并写入。

| 键 | 类型 | 说明 |
|---|---|---|
| `current_node` | `str\|null` | 当前正在执行的节点名，用于异常定位 |
| `status` | `str` | 流程最终状态，取值见下表 |
| `short_circuit_reason` | `str\|null` | 短路原因（`small_talk` / `out_of_scope`），短路时由 Pipeline 写入 |
| `error` | `dict\|null` | 未捕获异常时写入，含 `node`、`type`、`message` |

**`status` 枚举：**

| 值 | 含义 | 触发时机 |
|---|---|---|
| `running` | 执行中 | 初始值 |
| `completed` | 正常完成 | Node4 执行成功后 |
| `short_circuited` | 意图短路 | 闲聊/超出范围，Node1 后触发 |
| `rejected` | 合规拦截 | Node2 合规不通过 |
| `pending_review` | 等待人工审核 | Node2 触发人工审核规则 |
| `failed` | 执行失败 | 关键 Skill 失败 或 未捕获异常 |

---

### 3.5 运行时私有键

这两个键**不在 `make_initial_state()` 中定义**，由运行时按需挂载，**不落库**。

| 键 | 写入方 | 说明 |
|---|---|---|
| `_sse_queue` | `views.chat()` | `asyncio.Queue`，Pipeline 向此 `put_nowait()` 推送 SSE 事件，`event_generator()` 消费 |
| `_review_task_id` | `pipeline.run()` | 人工审核任务创建后写入，供 Pipeline 后续流转识别 |

---

## 四、Pipeline 分支决策树

```
Pipeline.run(state)
│
├─ Node1 执行
│   ├─ category in (small_talk, out_of_scope)?
│   │   └─ YES → status=short_circuited，推送礼貌提示 → 返回（不写审计）
│   └─ needs_clarification=true?
│       └─ YES → status=completed，推送澄清问题 → 返回（不写审计）
│
├─ Node2 执行
│   ├─ compliance.passed=false?
│   │   └─ YES → status=rejected，推送拒绝原因 → 写审计（异步） → 返回
│   └─ human_review.required=true?
│       └─ YES → 持久化 state 快照 → status=pending_review，推送任务号 → 写审计（异步） → 返回
│
├─ Node3 执行（Skill 并发 + RAG 并发）
│   └─ 写操作 Skill 关键失败?
│       └─ YES → status=failed，推送错误 → 写审计（异步） → 返回
│
├─ Node4 执行（LLM 流式，实时推送 SSE token）
│   └─ status=completed
│
└─ Node5 执行（异步，不阻塞响应）
    └─ finally 块：_signal_sse_done() 推送 done 事件 + None 哨兵
```

---

## 五、SSE 事件类型

前端通过 `event_generator()` 收到的事件类型：

| `event` 字段 | 触发时机 | `data` 内容 |
|---|---|---|
| `token` | Node4 LLM 流式输出每个 chunk，或短路/拦截时一次性推送文本 | `{"text": "..."}` |
| `content_blocked` | Node4 检测到合规用语违规 | `{"type": "compliance_violation", "message": "..."}` |
| `validation_warning` | Node4 检测到数值不一致 | `{"type": "number_mismatch", "message": "..."}` |
| `done` | Pipeline `finally` 块，流结束信号 | `{"turn_id": "...", "status": "...", "token_usage": {...}}` |

> 前端收到 `done` 事件后即可关闭 SSE 连接。`None` 哨兵是给 `event_generator()` 内部用的退出信号，不会发送到前端。

---

## 六、人工审核恢复路径

当 `status=pending_review` 时，state 快照被持久化到 DB。
审核人操作后，`pipeline.resume_from_node3()` 从 Node3 重新恢复执行：

```
审核人 POST /agent.review.approve
    → service.process_review_decision()
    → review_persistence.resume_after_review()
    → pipeline.resume_from_node3(state)
        → Node3（重新执行 Skill）
        → Node4（非流式调用，无 _sse_queue）
        → Node5（写审计）
    → service.save_turn_messages()  ← 保存助手回复
```

用户可通过 `POST /agent.task.status` 轮询任务状态，审核通过后可取到助手回复。
