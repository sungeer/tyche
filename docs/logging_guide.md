# 日志记录规范

本文档基于 hostess 项目的实际架构（views → service → repository → tasks），系统说明**何处、何时、记录什么级别的日志**。

---

## 一、先理解日志的目的

日志不是给代码"加注释"，而是给**运行中的系统**留下可查询的证据链。  
写日志前问自己一个问题：**"当这里出问题时，我需要知道什么？"**

---

## 二、日志级别速查

项目使用 loguru，级别语义如下：

| 级别 | 方法 | 用途 |
|------|------|------|
| DEBUG | `logger.debug()` | 开发调试，生产不输出 |
| INFO | `logger.info()` | 关键业务节点，正常流程的里程碑 |
| WARNING | `logger.warning()` | 不影响当前请求但需要关注的异常状态 |
| ERROR | `logger.error()` | 可预期的失败（通常已被 BusinessError 处理） |
| EXCEPTION | `logger.exception()` | 未预期的系统级异常，**自动附带堆栈** |

> 本项目 `setup_logger()` 中：INFO/DEBUG → stdout，WARNING 及以上 → stderr。  
> `logger.exception()` 级别为 ERROR，但会额外打印完整 traceback。

---

## 三、各层规范

### 3.1 views 层（`domains/*/views.py`）

**职责：** 解析请求、调用 service、返回响应。  
**结论：views 层通常不需要日志。**

原因：
- 请求入口的访问日志应由中间件统一处理，不该散落在每个 view 函数里。
- 业务结果由 service 层负责记录。
- 异常由 `handlers.py` 统一捕获并记录。

**例外情况：** 如果某个接口有特殊的安全审计需求（如敏感操作），才在 view 里加：

```python
# 敏感操作：记录操作人和目标（安全审计用）
async def delete_user(request):
    target_id = body['user_id']
    operator = request.user.username
    logger.warning(f"[AUDIT] {operator} 删除用户 {target_id}")
    await user_service.delete(target_id)
    return ok()
```

---

### 3.2 service 层（`domains/*/service.py`）

**职责：** 编排业务流程，做业务判断。  
**这是最需要日志的层。**

**记录什么：**

```python
# ✅ 记录关键业务决策点
async def create_item(user_id: int, roles: list[str], data: dict):
    if '管理员' not in roles:
        logger.warning(f"用户 {user_id} 越权尝试创建 item，roles={roles}")
        raise BusinessError(BizCode.FORBIDDEN)

    # ✅ 记录耗时或重要的外部依赖调用（如 AI 推理、第三方接口）
    logger.info(f"[create_item] 开始为用户 {user_id} 创建 item，数量={data.get('quantity')}")

    item = await item_repository.insert(user_id, data)

    # ✅ 记录业务完成结果（带关键 ID，方便排查）
    logger.info(f"[create_item] 成功，item_id={item.id}，user_id={user_id}")
    return item
```

**不记录什么：**

```python
# ❌ 不要记录每次普通查询——高频只读操作会淹没日志
async def get_item(item_id: int):
    logger.info(f"查询 item {item_id}")  # 没意义，每秒可能几百次
    return await item_repository.query_one(item_id)
```

**规则总结：**

| 场景 | 级别 | 记录 |
|------|------|------|
| 重要业务流程开始/完成 | INFO | 操作名 + 关键参数（user_id、entity_id） |
| 业务判断导致流程中断 | WARNING | 判断条件 + 当前值 |
| 调用外部服务/AI/第三方 | INFO | 调用前 + 调用后耗时结果 |
| 高频普通查询 | 不记录 | — |

---

### 3.3 repository 层（`domains/*/repository.py`）

**职责：** 执行 SQL，不含业务逻辑。  
**结论：repository 层一般不写日志。**

原因：
- repository 只是执行 SQL，业务含义由 service 层理解。
- SQL 执行的调试信息应通过 SQLAlchemy 的 `echo=True` 开关控制，不是手动 logger。
- 如果 SQL 执行失败，会抛出异常，由上层的 `handlers.py` 统一捕获。

**例外：慢查询或关键写操作可在 service 层记录时间，不在 repository 里加日志：**

```python
# service 层负责感知慢操作，不是 repository
import time

async def rebuild_index(kb_id: int):
    start = time.monotonic()
    await doc_repository.rebuild(kb_id)
    elapsed = time.monotonic() - start
    if elapsed > 2:
        logger.warning(f"[rebuild_index] 慢操作，kb_id={kb_id}，耗时={elapsed:.2f}s")
```

---

### 3.4 middleware 层（`middleware/guards.py`）

**职责：** JWT 验证，填充 `request.user`。  
**记录什么：**

```python
# ✅ Token 解析失败（可能是攻击或客户端 bug，值得记录）
logger.warning(f"[JWT] Token 解析失败，path={request.url.path}，reason={str(e)}")

# ✅ Token 过期（正常但需感知频率）
logger.info(f"[JWT] Token 已过期，path={request.url.path}")
```

```python
# ❌ 不要记录每个正常通过的请求——太噪
logger.info(f"[JWT] 验证通过，user_id={user_id}")  # 高频，没价值
```

---

### 3.5 exception handlers（`core/handlers.py`）

**这里是日志的最后防线，已经有兜底处理。**

```python
# ✅ 已有，保持不变——500 级别必须记录堆栈
async def server_error(request, exc):
    logger.exception(f'unhandled exception on [{request.method}] [{request.url.path}]')
    ...
```

**BusinessError 不需要在 handler 里记录**，因为它是预期内的业务失败，由 service 层在抛出前决定要不要记。

---

### 3.6 tasks 层（`domains/*/tasks.py`）

**异步任务和定时任务是日志最重要的地方之一。**

原因：任务在后台执行，没有 HTTP 响应，出错后**唯一的排查手段就是日志**。

```python
@huey.task(retries=3, retry_delay=60)
def process_item_export(item_ids: list[int]):
    # ✅ 记录任务入参（便于复现）
    logger.info(f"[export] 开始，item_ids={item_ids[:10]}...")  # 截断防止超长

    try:
        # 执行逻辑...
        logger.info(f"[export] 完成，共处理 {len(item_ids)} 条")
    except Exception as e:
        # ✅ 任务内部异常必须手动记录，huey 不会自动打日志
        logger.exception(f"[export] 失败，item_ids={item_ids[:10]}，error={e}")
        raise  # 让 huey 的 retries 机制生效


@huey.periodic_task(crontab(hour='2', minute='0'))
def cleanup_expired_items():
    # ✅ 定时任务：记录开始、结束、处理数量
    logger.info("[cleanup] 开始清理过期 items")
    count = do_cleanup()
    logger.info(f"[cleanup] 完成，删除 {count} 条")
```

---

## 四、什么情况坚决不加日志

| 反模式 | 原因 |
|--------|------|
| 每个函数入口都加 `logger.info("进入 xxx 函数")` | 是注释，不是日志，噪声极大 |
| 记录密码、Token、身份证、手机号等敏感字段 | 安全合规问题 |
| `logger.info` 记录正常的高频只读查询 | 每秒几百条会淹没真正有价值的日志 |
| 捕获异常后 `logger.error` 又再次 `raise` | 导致重复记录，让排查更混乱 |
| `logger.debug` 留在生产代码里但从不清理 | 本项目 setup_logger 不输出 DEBUG，可以留，但要控制数量 |

---

## 五、格式约定

本项目 logger 格式为：`时间 - 级别 - 消息`，消息部分建议：

```
[模块名/操作名] 动作描述，key1=val1，key2=val2
```

示例：
```
[create_item] 开始，user_id=42，quantity=3
[create_item] 成功，item_id=1001，user_id=42
[JWT] Token 解析失败，path=/api/order，reason=Signature verification failed
[export] 完成，共处理 500 条
```

用 `[方括号标签]` 开头的好处：可以用 `grep "\[create_item\]"` 快速过滤出某个操作的全部日志。

---

## 六、一句话总结各层

| 层 | 是否加日志 | 记录什么 |
|----|-----------|---------|
| views | 极少 | 仅安全审计 |
| **service** | **重点** | **业务关键节点、决策、外部调用** |
| repository | 不加 | 交给 SQLAlchemy echo 或上层 |
| middleware | 少量 | Token 异常 |
| handlers | 已有兜底 | 500 级别保持 logger.exception |
| **tasks** | **重点** | **任务入参、完成结果、内部异常** |
