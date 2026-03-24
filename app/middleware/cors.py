from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# cors 配置允许的来源
origins = [
    'http://127.0.0.1:8000',  # 后端应用使用的端口
    'http://127.0.0.1:8080',  # 前端应用使用的端口
    'https://test.frontend.com',  # 测试环境
]

register_middlewares = [
    Middleware(
        CORSMiddleware,
        allow_origins=origins,  # allow_origins=['*']  # 允许所有来源
        allow_credentials=True,
        allow_methods=['*'],  # 允许所有方法
        allow_headers=['*'],  # 允许所有头部
    ),
]
