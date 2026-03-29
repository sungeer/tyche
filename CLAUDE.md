# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 项目概述

**hostess** 是一个基于 **Starlette**（ASGI）的异步 Python REST API，用于 RAG/知识库问答系统。（README 描述的是一个 Flask 博客——忽略它，内容已过时。）

## 启动服务器

```bash
# 开发环境（端口 7788 与测试脚本一致）
uvicorn app:app --port 7788

# 生产环境
uvicorn app:app --workers 4 --host 0.0.0.0 --port 8000
```

## 启动任务工作进程

```bash
huey_consumer worker.huey
```

## 运行测试

测试为 `tests/` 目录下的手动 HTTP 脚本，在服务器运行时单独执行：

```bash
python tests/task_list.py
```

## 安装依赖

项目没有 `requirements.txt`，请手动安装（参考 `docs/pip.sql`）：

```bash
python -m pip install asyncmy httpx sqlalchemy starlette orjson uvicorn loguru cryptography huey PyJWT
```

## 架构

### 入口点

- `app.py` — Uvicorn 目标；调用 `src.main` 中的 `create_app()`
- `worker.py` — Huey 消费者目标；导入所有任务模块后暴露 `src.core.worker.huey`

### 目录层级

```
src/
  main.py          # 应用工厂：路由、中间件、异常处理器、生命周期
  routes.py        # URL → 视图映射（所有路由均为 POST）
  core/            # 基础设施：DB、配置、Huey、JWT 工具、响应助手、异常
  domains/         # 按领域划分的业务逻辑（items/、users/）
  middleware/      # CORS + JWT 认证中间件
  utils/           # orjson 封装、JWT 助手、日期时间助手
```

### 请求流程

1. CORS 中间件（最外层）
2. `JWTAuthBackend`（`src/middleware/guards.py`）— 提取 Bearer token，将 `JWTUser(user_id, username, roles)` 填充至 `request.user`
3. Starlette 路由 → 领域 `views.py`
4. 视图调用领域 `service.py`，后者调用 `repository.py` 访问数据库
5. `src/core/response.py` 中的 `ok()` / `fail()` 助手返回基于 orjson 的响应

### 配置

`src/core/config.py` — 无 `.env` 文件，配置硬编码。当 `DEBUG=1` **或**在 Windows 上运行时自动启用开发模式。数据库地址：`mysql+asyncmy://root:admin@127.0.0.1:3306/hostess`。

### 关键模式

- **响应：** 始终使用 `src.core.response` 中的 `ok(data)` 或 `fail(biz_code)`
- **错误：** 抛出 `src.core.exceptions` 中 `BusinessError` 的子类；`src/core/handlers.py` 中的异常处理器会自动将其转换为 JSON
- **认证守卫：** 在视图上使用 `@requires('authenticated')` 或 `@requires('permission:name')`
- **异步任务：** 在领域的 `tasks.py` 中使用 `@huey.task()` 定义；在 `worker.py` 中导入以完成注册
- **业务错误码：** 在 `src/core/codes.py` 中以 `BizCode` 枚举定义（用户 1001–1xxx，商品 2001–2xxx，订单 3001–3xxx，支付 5001–5xxx）

### 数据库

MySQL 8.0+，通过 SQLAlchemy 异步驱动（`asyncmy`）访问。连接池：大小 20，最大溢出 20，回收时间 1800s。表结构见 `docs/roles.sql`，涵盖：用户、角色/权限、知识库、文档、分块、对话、查询历史。

### 任务队列

Huey（`MemoryHuey` — 进程内，非持久化）。Redis 后端已在 `src/core/worker.py` 中注释掉，生产环境请切换为 Redis。
