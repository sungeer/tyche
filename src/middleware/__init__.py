from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware

from src.middleware import guards
from src.core.config import settings

middleware = [
    # 第一个 = 最外层
    Middleware(
        CORSMiddleware,
        allow_origins=settings.origins,  # allow_origins=['*']  # 允许所有来源
        allow_credentials=True,
        allow_methods=['*'],  # 允许所有方法
        allow_headers=['*'],  # 允许所有头部
    ),
    # 第二个 = 内层
    Middleware(
        AuthenticationMiddleware,
        backend=guards.JWTAuthBackend(),
        on_error=guards.on_auth_error
    ),
]
