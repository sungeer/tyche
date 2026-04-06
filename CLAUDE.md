# Hostess 项目规范

## 项目结构

```
src/
  main.py          # create_app() 工厂
  routes.py        # 所有路由集中注册
  core/            # 基础设施（db、config、logger、response 等）
  domains/         # 业务领域，每个域三层：repository / service / views
  middleware/      # 中间件（RunId → CORS → Auth）
  utils/           # 无副作用纯工具函数
```

`app.py` 是 Web 进程入口，`worker.py` 是 Huey 消费者进程入口

## 架构约定

- **路由风格**：点号命名法（`/auth.token`、`/task.list`），不用 RESTful 斜杠风格
- **视图**：`async` 函数，不用类视图
- **domain 三层职责**：
  - `repository.py`：只负责 SQL，接收 `conn`，不抛业务异常
  - `service.py`：业务逻辑，调 repository，做业务判断
  - `views.py`：解析请求参数，调 service，返回响应
- **数据库**：同步 SQLAlchemy Core + `text()` 手写 SQL，通过 `db_threadpool` offload 到线程池
- **任务**：Huey，定义在各 domain 的 `tasks.py`，worker 通过 import 副作用注册

## 响应格式

- 业务成功使用 `ok(data)` 返回 `{"code": 0, "msg": "success", "data": ...}`

- 业务失败（HTTP 200）使用 `fail(BizCode.xxx)` 返回 `{"code": 3004, "msg": "...", "data": null}`

## 异常体系

- `BusinessError` — 业务失败，HTTP 200 + 非零 code
- `BadRequestError` — 参数错误，HTTP 400
- `TokenExpiredError` / `TokenInvalidError` — JWT 问题，HTTP 401

## 线程池命名语义

- `db_threadpool`：数据库阻塞 IO 专用
- `bio_threadpool`：其他阻塞 IO

## 追踪机制

每个请求/任务都有 `run_id`，通过 `ContextVar` 传递，统一注入日志
