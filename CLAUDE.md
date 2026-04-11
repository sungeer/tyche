# Hostess 项目规范

## 项目结构
`app.py` 是 Web 进程入口，`worker.py` 是 Huey 消费者进程入口
```
src/
  main.py          # create_app() 工厂
  routes.py        # 所有路由集中注册
  core/            # 基础设施（db、config、logger、response 等）
  domains/         # 业务领域，每个域三层：repository / service / views
  middleware/      # 中间件（RunId → CORS → Auth）
  utils/           # 无副作用纯工具函数
```

## 路由风格
- 禁止使用 RESTful 斜杠风格
- 优先采用点号命名法（`/auth.token`、`/task.list`）
- 所有路由统一使用 POST 方法，禁止使用 GET

## 任务调度
- 采用 Huey，定义在各 domain 的 `tasks.py`
- worker 通过 import 副作用注册

## domain 职责
- `repository.py`：只负责 SQL，接收 `conn`，不抛业务异常
- `service.py`：业务逻辑，调 repository，做业务判断；资源不存在、状态非法等业务语义判断必须在此层抛出对应异常
- `views.py`：解析请求参数，调 service，返回响应；JSON body 统一使用 `serial.from_json(await request.body())` 解析，禁止使用 `await request.json()`
  - 只做请求边界的参数格式校验（如必填字段缺失时抛 `BadRequestError`）
  - 禁止对 Service 返回值做业务判断（如 `if not result` 后抛异常），业务语义由 Service 负责

## 响应格式
- 业务成功使用 `ok(data)` 返回 `{"code": 0, "msg": "success", "data": ...}`
- 业务失败（HTTP 200）使用 `fail(BizCode.xxx)` 返回 `{"code": 3004, "msg": "...", "data": null}`

## 异常体系
- `BusinessError` — 业务失败，HTTP 200 + 非零 code
- `BadRequestError` — 参数错误，HTTP 400
- `TokenExpiredError` / `TokenInvalidError` — JWT 问题，HTTP 401

## HTTP 状态码规范
- `fail()` 专用于业务失败，HTTP 状态码始终为 200，禁止用它返回 4xx/5xx
- 未登录（401）：使用 `@requires('authenticated', status_code=401)` 装饰器，禁止用 `fail(401, ...)`
- 无权限（403）：使用 `raise HTTPException(status_code=403, detail='...')` 或 `@requires(scope, status_code=403)`，禁止用 `fail(403, ...)`
- 401 和 403 均有对应的全局 handler（`auth_error` / `forbidden_error`），会统一返回标准 JSON 格式

## 线程池命名语义
- `db_threadpool`：数据库阻塞 IO 专用
- `bio_threadpool`：其他阻塞 IO

## 异步 IO 规范
- HTTP 客户端统一使用 `httpx` 异步调用，禁止使用 `requests`
- 数据库操作保持同步 SQLAlchemy + `db_threadpool` offload，禁止使用异步 MySQL 驱动（如 aiomysql）
- 原因：异步 MySQL 驱动缺乏维护、稳定性差；`httpx` 则是活跃且稳定的项目，原生支持 async/await，无需线程池中转

## 追踪机制
- 每个请求/任务都有 `run_id`，通过 `ContextVar` 传递，统一注入日志

## Python规范
- 严格使用 Python 3.14 版本的语法和标准库特性，不需要考虑低版本的兼容
- 绝对遵守 PEP 8 规范
- 优先采用显式设计，拒绝任何晦涩难懂的写法
- 禁止使用隐式的魔法方法，保持代码逻辑的直观可见
- 禁止使用类型注解（Type Hints）
- 禁止使用通配符导入（from xxx import *）
- 禁止使用 global 和 nonlocal
- 字符串格式化优先使用 f-string
- 布尔值判断禁止使用 == True / == False，直接使用变量或 not
- 从序列中按名称提取元素时，优先使用解包而非硬编码下标（如 `first, *rest = items` 或 `a, b = pair`），避免 `items[0]`、`items[1]` 这类写法

## Web框架规范
- Web 框架使用 Starlette 1.0.0 版本
- 禁止使用 FastAPI

## 数据库规范
- 同步 SQLAlchemy Core + `text()` 手写 SQL，通过 `db_threadpool` offload 到线程池
- 数据库采用 MySQL 8.4.8 版本，不需要考虑低版本的兼容
- 数据库驱动使用 mysqlclient 2.2.8 版本
- 表结构设计严格遵循"三范式"，避免数据冗余
- 绝对禁止使用物理外键约束，在生成的所有DDL语句或表结构设计中，严禁出现 `FOREIGN KEY` 关键字
- 优先采用"软关联"设计，表与表之间的关联关系必须且只能通过"命名约定"来实现（即在从表中增加一个字段，使用 `{主表名单数}_id` 的格式来指向主表的主键）
    - 示例：关联 `user` 表，字段名必须为 `user_id`（类型通常与主表主键一致，如 `BIGINT UNSIGNED`）
    - 示例：关联 `order` 表，字段名必须为 `order_id`
- 所有的软关联字段（如 `user_id`），在其 `COMMENT` 中必须显式说明其关联的表，格式为："关联xxx表的主键"
- 对于软关联字段（如 `user_id`），如果业务场景涉及基于该字段的查询，请务必在设计中单独为其添加普通索引（`INDEX` 或 `KEY`），以弥补没有物理外键带来的查询性能问题
- 禁止出现 SQL 慢查询语句
- SQL 关键字必须大写
- 表名、字段名无需使用反引号包裹
- 严禁将 SQL 语句写成一整行，必须按照逻辑层级进行换行与缩进，保持极高的可读性
- 数据库工具包使用 SQLAlchemy 2.0.49 版本
- 禁止使用 ORM
- 禁止使用字符串拼接 SQL
- 严格使用 `sqlalchemy` 的 `engine` 的参数化绑定（即 `text('SELECT * FROM users WHERE id = :uid')` 配合 `{'uid': 1}`）防止 SQL 注入
- 所有表必须包含 id 作为自增主键，使用 BIGINT UNSIGNED 类型
- 字段默认值规范：禁止使用 NULL 作为字符串/数值型字段的默认值
- 时间字段统一使用 DATETIME(3) 存储毫秒精度，统一使用 UTC 时区
- 软删除字段统一命名为 deleted_at，类型为 BIGINT UNSIGNED DEFAULT 0（0 表示未删除，大于 0 表示已删除的毫秒级时间戳）
- 创建时间字段统一命名为 created_at，更新时间字段统一命名为 updated_at
- 索引命名规范：普通索引用 idx_表名_字段名，唯一索引用 uk_表名_字段名
- 事务隔离级别保持默认的 READ COMMITTED
- 禁止在循环中执行 SQL，必须使用批量操作
