# 项目：Agent应用系统后端API

## 技术栈
- Python 3.14 + Starlette 1.0.0（ASGI）
- SQLAlchemy（mysqlclient）+ MySQL 8.0+
- Uvicorn + JWT + Huey
- MapStruct（对象映射）

## 常用命令
- mvn spring-boot:run - 启动开发服务器
- mvn test - 运行测试
- mvn flyway:migrate
- 数据库迁移