# run_id 的生成与传递

> 本文是 [logging_agent_guide.md](logging_agent_guide.md) 的配套实现，解决 `run_id` 如何在
> view → service → LLM 调用 → 工具调用等多层函数中自动传递，而不需要每个函数都加参数。

---

## 一、核心工具：Python `contextvars`

直觉上你可能想把 `run_id` 当参数一层层传下去：

```python
async def create_order(request):
    run_id = new_run_id()
    await item_service.create_item(run_id, user_id, body)   # 传进去

async def create_item(run_id, user_id, data):
    await call_llm(run_id, prompt)                          # 继续传
    await call_tool(run_id, tool_name, args)                # 继续传
```

这样每个函数签名都被污染，非常难维护。

**正确做法是用标准库的 `contextvars.ContextVar`。**  
它的特性：
- 在同一个 async 调用链中，下游代码可以直接读取，不需要参数传递
- async 安全：每个并发请求拥有独立的上下文，不会互相污染（这是它和全局变量的本质区别）
- 在 asyncio 中，`await` 调用会自动继承当前上下文

---

## 二、实现步骤

### 第一步：新建 `src/core/context.py`

```python
import uuid
from contextvars import ContextVar

# 当前请求/Agent 运行的唯一 ID
# default='-' 是兜底值，在没有设置 run_id 的情况下日志不会报错
run_id_var: ContextVar[str] = ContextVar('run_id', default='-')


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]  # 例如 'a3f9c1b2'
```

---

### 第二步：修改 `src/core/logger.py`，让日志自动读取 run_id

用 loguru 的 `patcher` 机制，每次写日志时自动从 context 中取出 `run_id` 注入：

```python
import sys
from loguru import logger
from src.core.context import run_id_var


def setup_logger():
    logger.remove()

    # patcher：每条日志写入前自动执行，把 run_id 注入 extra
    def inject_run_id(record):
        record['extra']['run_id'] = run_id_var.get('-')

    logger.configure(patcher=inject_run_id)

    logger.add(
        sink=sys.stdout,
        format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - [run:{extra[run_id]}] {message}',
        level='INFO',
        diagnose=False,
        backtrace=False,
        colorize=False,
        enqueue=True,
    )
```

之后所有层的代码只需 `logger.info("xxx")`，`run_id` 会自动出现在日志里。

---

### 第三步：在 view 层生成并设置 run_id

**`run_id` 应该在请求的入口处生成**——也就是 view 函数里，在调用 service 之前：

```python
# src/domains/items/views.py
from starlette.authentication import requires
from src.core.response import ok
from src.core.context import run_id_var, new_run_id
from src.domains.items import service as item_service
from src.utils import serial
from loguru import logger


@requires('order:create')
async def create_order(request):
    # 在请求入口生成 run_id，后续所有日志自动携带
    run_id_var.set(new_run_id())

    body = serial.from_json(await request.body())
    user_id = request.user.user_id

    logger.info(f"[create_order] 收到请求，user_id={user_id}")

    order = await item_service.create_item(user_id, request.user.roles, body)

    logger.info(f"[create_order] 响应完成，order_id={order.id}")
    return ok(data={'order_id': order.id}, msg='下单成功')
```

---

### 第四步：service 层直接用 logger，无需感知 run_id

```python
# src/domains/items/service.py
from loguru import logger
from src.domains.items import repository as item_repository
from src.core.llm import call_llm       # 假设的 LLM 调用模块
from src.core.tools import call_tool    # 假设的工具调用模块


async def create_item(user_id: int, roles: list[str], data: dict):
    # 直接写 logger，run_id 自动附加——不需要任何额外参数
    logger.info(f"[create_item] 开始，user_id={user_id}，data={data}")

    # 调用 LLM
    logger.info(f"[create_item] 调用 LLM 提取意图")
    intent = await call_llm(prompt=f"用户意图分析：{data}")
    logger.info(f"[create_item] LLM 返回，intent={intent}")

    # 调用工具
    logger.info(f"[create_item] 调用工具 search_kb，intent={intent}")
    kb_result = await call_tool('search_kb', {'query': intent})
    logger.info(f"[create_item] 工具返回，hits={len(kb_result)}")

    item = await item_repository.insert(user_id, data)
    logger.info(f"[create_item] 写库完成，item_id={item.id}")

    return item
```

---

## 三、实际日志效果

一次 Agent 运行产生的日志，`run_id` 统一为 `a3f9c1b2`：

```
2026-04-04 10:23:01.001 - INFO - [run:a3f9c1b2] [create_order] 收到请求，user_id=42
2026-04-04 10:23:01.003 - INFO - [run:a3f9c1b2] [create_item] 开始，user_id=42，data={...}
2026-04-04 10:23:01.005 - INFO - [run:a3f9c1b2] [create_item] 调用 LLM 提取意图
2026-04-04 10:23:02.213 - INFO - [run:a3f9c1b2] [create_item] LLM 返回，intent=购买商品
2026-04-04 10:23:02.215 - INFO - [run:a3f9c1b2] [create_item] 调用工具 search_kb，intent=购买商品
2026-04-04 10:23:02.387 - INFO - [run:a3f9c1b2] [create_item] 工具返回，hits=5
2026-04-04 10:23:02.401 - INFO - [run:a3f9c1b2] [create_item] 写库完成，item_id=1001
2026-04-04 10:23:02.403 - INFO - [run:a3f9c1b2] [create_order] 响应完成，order_id=1001
```

查这一次完整运行：

```bash
grep "run:a3f9c1b2" app.log
```

---

## 四、特殊情况：Huey 异步任务

`contextvars` 在 **asyncio 调用链**中自动传递，但 Huey 任务运行在独立的 worker 进程里，context 无法自动携带过去。

解决方式：把 `run_id` 作为**普通参数**传入任务，在任务内部手动设置：

```python
# view 层触发任务时，把 run_id 传进去
@requires('order:create')
async def create_order(request):
    run_id = new_run_id()
    run_id_var.set(run_id)

    # 显式把 run_id 传给 Huey 任务
    process_item_export.schedule(args=([101, 102, 103], run_id), delay=0)

    return ok()
```

```python
# src/domains/items/tasks.py
from src.core.context import run_id_var
from src.core.queue import huey
from loguru import logger


@huey.task(retries=3, retry_delay=60)
def process_item_export(item_ids: list[int], run_id: str = '-'):
    # 手动恢复 run_id，后续 logger 自动携带
    run_id_var.set(run_id)

    logger.info(f"[export] 开始，item_ids 数量={len(item_ids)}")
    try:
        # 执行逻辑...
        logger.info(f"[export] 完成")
    except Exception as e:
        logger.exception(f"[export] 失败，error={e}")
        raise
```

---

## 五、更进一步：在中间件统一生成（可选）

如果想让**每个请求**（包括非 Agent 路由）都自动拥有 `run_id`，可以在 `JWTAuthBackend` 或单独的中间件里统一设置，view 层就不用手动调用了：

```python
# src/middleware/guards.py（在 authenticate 末尾追加）
from src.core.context import run_id_var, new_run_id

class JWTAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        # ...现有 JWT 验证逻辑...

        # 每个请求统一分配 run_id（无论是否登录都会执行）
        run_id_var.set(new_run_id())

        return AuthCredentials(roles), JWTUser(user_id, username, roles)
```

这样 view 层不需要任何改动，所有日志天然带 `run_id`。

---

## 六、总结

| 问题 | 答案 |
|------|------|
| run_id 在哪里生成 | view 层入口（或统一放到 middleware） |
| 如何传递到 service / LLM / 工具调用 | `contextvars.ContextVar`，自动传递，无需函数参数 |
| 日志如何自动附加 run_id | `logger.configure(patcher=...)` 每次写日志时从 context 读取 |
| Huey 任务怎么办 | 显式传参，任务内 `run_id_var.set(run_id)` 手动恢复 |
