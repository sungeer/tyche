from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from src.middleware import cors

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=cors.origins,  # allow_origins=['*']  # 允许所有来源
        allow_credentials=True,
        allow_methods=['*'],  # 允许所有方法
        allow_headers=['*'],  # 允许所有头部
    ),
]
