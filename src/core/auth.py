import functools

from src.core.exceptions import UnauthorizedError, ForbiddenError


def login_required(func):
    """
    校验用户是否已登录
    未登录抛 UnauthorizedError
    """

    @functools.wraps(func)
    async def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise UnauthorizedError()
        return await func(request, *args, **kwargs)

    return wrapper


def permission_required(scope):
    """
    校验用户是否持有指定 scope
    未登录抛 UnauthorizedError
    无权限抛 ForbiddenError
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise UnauthorizedError()
            if scope not in request.user.roles:
                raise ForbiddenError(f'需要 {scope} 权限')
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
