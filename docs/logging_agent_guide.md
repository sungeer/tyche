# Agent 应用日志补充：结构化输出与 stdout/stderr

> 本文是 [logging_guide.md](logging_guide.md) 的补充，针对 Agent 应用场景和具体部署环境的两个常见问题。

---

## 一、是否需要结构化日志（structlog / JSON 格式）

**结论：不需要。**

structlog / JSON 格式日志的价值在于**机器解析**——Elasticsearch、Loki、Datadog 这类系统能按字段过滤查询。  
人工 grep 日志文件时，JSON 是负担不是收益：

```
# JSON 格式——人读很痛苦
{"time":"2026-04-04T10:23:01","level":"INFO","event":"LLM call","agent":"planner","tokens":1203,"latency":1.24}

# 纯文本——人读很舒服，grep 一样好用
2026-04-04 10:23:01 - INFO - [planner] LLM call 完成，tokens=1203，latency=1.24s
```

等团队引入日志聚合系统时再迁移到结构化格式，现阶段引入只增加复杂度。

---

## 二、Agent 应用的核心日志难题：串联一次完整运行

Agent 应用日志的真正挑战不是格式，而是**如何把一次 Agent 运行的所有步骤串起来**（LLM 调用、工具调用、重试等可能跨越多个函数）。

解决方案：每次 Agent 运行生成唯一 `run_id`，用 loguru 的 `bind()` 注入到后续所有日志中：

```python
from loguru import logger
import uuid

async def run_agent(user_query: str):
    run_id = str(uuid.uuid4())[:8]
    log = logger.bind(run_id=run_id)

    log.info(f"[agent] 开始，query={user_query[:50]}")
    log.info(f"[planner] 调用 LLM，model=claude-sonnet-4-6")
    log.info(f"[tool] 执行 search，keyword={keyword}")
    log.info(f"[agent] 完成，steps=3，total_tokens=2401")
```

在 `setup_logger()` 的 format 中加入 `run_id` 字段：

```python
logger.add(
    sink=sys.stdout,
    format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - [{extra[run_id]}] {message}',
    ...
)
```

查一次完整 Agent 运行只需要一条命令：

```bash
grep "a3f9c1b2" app.log
```

---

## 三、stdout vs stderr 分流：建议全部输出到 stdout

**结论：不需要分流，全部走 stdout。**

部署链路为 `uvicorn worker → gunicorn → 日志文件`，分流的问题：

- gunicorn 默认把 stdout 和 stderr 写入**不同文件**
- 人工排查时需要打开两个文件，对照时间戳拼凑事件顺序
- 分流的意义是让监控系统订阅 stderr 自动报警——没有这个系统时好处为零

**`setup_logger()` 改法：**

```python
def setup_logger():
    logger.remove()
    logger.add(
        sink=sys.stdout,        # 全部走 stdout，gunicorn 统一收集
        format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {message}',
        level='INFO',
        diagnose=False,
        backtrace=False,
        colorize=False,
        enqueue=True,
    )
```

gunicorn 启动时用 `--capture-output` 把 stdout/stderr 统一写入同一个文件：

```bash
gunicorn app:app --capture-output --log-file logs/app.log
```

---

## 四、总结

| 问题 | 结论 | 原因 |
|------|------|------|
| 需要 structlog 吗 | 不需要 | 没有日志系统，人工查询，纯文本更易读 |
| Agent 应用如何串联日志 | loguru `bind(run_id=...)` | 每次运行生成唯一 ID，一行 grep 查全程 |
| stderr 分流 | 不需要，全走 stdout | 没有监控订阅 stderr，分流只会让人工查询更难 |
