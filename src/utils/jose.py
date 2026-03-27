from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.core.config import settings
from src.core.exceptions import TokenExpiredError, TokenInvalidError


# 生成 JWT Access Token
def create_access_token(subject, extra_data=None, expires_minutes=None) -> str:
    # token = create_access_token(subject=user.id, extra_data={'role': 'admin'})
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_access_token_expire_minutes
    )  # expires_minutes 过期时间 分钟 int

    payload = {
        'sub': str(subject),  # subject 通常是 user_id str, int
        'exp': expire,
        'iat': datetime.now(timezone.utc),   # 签发时间
        'type': 'access',
    }

    if extra_data:
        payload.update(extra_data)  # extra_data 需要附加到 payload 的额外字段 dict

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# 生成 JWT Refresh Token 过期时间更长
def create_refresh_token(subject) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )

    payload = {
        'sub': str(subject),  # subject 通常是 user_id str, int
        'exp': expire,
        'iat': datetime.now(timezone.utc),
        'type': 'refresh',
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# 解析 Payload 不做业务校验
def decode_token(token: str):
    # 解析 JWT 返回原始 payload
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload  # dict

    except ExpiredSignatureError:
        raise TokenExpiredError()  # token 已过期

    except InvalidTokenError:
        raise TokenInvalidError()  # token 非法或格式错误


# 验证 Token 做业务校验 (中间件里验证)
def verify_access_token(token: str):
    # 验证 Access Token 合法性 返回 payload
    payload = decode_token(token)

    if payload.get('type') != 'access':
        raise TokenInvalidError()  # token 类型不符或非法

    return payload  # dict


# 验证 Refresh Token
def verify_refresh_token(token: str):
    # 验证 Refresh Token 合法性 返回 payload
    payload = decode_token(token)

    if payload.get('type') != 'refresh':
        raise TokenInvalidError()

    return payload


# 便捷函数 (只需要拿 user_id)
def get_subject(token: str) -> str:
    # 从 Access Token 中直接提取 subject（user_id）
    payload = verify_access_token(token)
    return payload['sub']
