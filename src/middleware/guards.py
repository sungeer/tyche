from loguru import logger
from starlette.authentication import AuthenticationBackend, AuthenticationError, AuthCredentials, BaseUser

from src.core.response import Response
from src.utils import jose
from src.core.exceptions import TokenExpiredError, TokenInvalidError


class JWTUser(BaseUser):

    def __init__(self, user_id, username, roles):
        self.user_id = user_id  # int
        self.username = username  # str
        self.roles = roles  # list[str]

    @property
    def is_authenticated(self):
        return True

    @property
    def display_name(self):
        return self.username


# 认证中间件
class JWTAuthBackend(AuthenticationBackend):

    async def authenticate(self, conn):
        if 'Authorization' not in conn.headers:
            return None  # 匿名用户

        auth = conn.headers['Authorization']
        try:
            scheme, token = auth.split()
            if scheme.lower() != 'bearer':
                return None
            payload = jose.verify_access_token(token)
        except TokenExpiredError as e:
            logger.info(f'[JWT] Token 已过期，path={conn.url.path}')
            raise AuthenticationError(e.msg)
        except TokenInvalidError as e:
            logger.warning(f'[JWT] Token 非法，path={conn.url.path}，reason={str(e)}')
            raise AuthenticationError(e.msg)
        except Exception:
            logger.warning(f'[JWT] Token 解析失败，path={conn.url.path}')
            raise AuthenticationError('Invalid JWT token')  # 此处异常不会越出中间件

        user_id = payload['user_id']
        username = payload['username']
        roles = payload.get('roles', [])  # ['order:create', 'order:read']

        # roles 同时写入 AuthCredentials 和 JWTUser
        return AuthCredentials(roles), JWTUser(user_id, username, roles)


def on_auth_error(request, exc):
    return Response(
        {'code': 401, 'msg': str(exc), 'data': None},
        status_code=401,
    )
