# Hostess 项目规范

## 个人偏好
- 使用中文回复
- 每次回答的开头必须先称呼`迅哥`
- 代码注释使用中文
- 可读性永远排在第一位
- 对于不确定的，请说`我不确定`，禁止编造

## 沟通风格
- 遇到不明确的先问
- 给出方案时说明取舍

## Python 代码风格
- Python 代码里的"字符串"类型必须优先使用单引号`'`
- 禁止使用 Python 里的`global`关键字
- 如果某行代码保持不变，则禁止删除该行代码所对应的已有注释

## 路由风格
- 采用点号命名法（`/auth.token`、`/task.list`）
- 所有路由统一使用 POST 方法

## 环境要求
- Python 3.13
- MySQL 8.4.9 LTS
- langgraph 1.1.10
- starlette 1.0.0
- langchain 1.2.17
- aiomysql 0.3.2
- uvicorn 0.46.0
- SQLAlchemy 2.0.49
