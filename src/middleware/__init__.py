from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware

from src.core.config import settings
from src.middleware import tracing
from src.middleware import guards

middleware = [
    Middleware(tracing.RunIdMiddleware),  # 最外层 最先执行
    Middleware(
        CORSMiddleware,
        allow_origins=settings.origins,  # allow_origins=['*']  # 允许所有来源
        allow_credentials=True,
        allow_methods=['*'],  # 允许所有方法
        allow_headers=['*'],  # 允许所有头部
    ),
    Middleware(
        AuthenticationMiddleware,
        backend=guards.JWTAuthBackend(),
        on_error=guards.on_auth_error
    ),
]
