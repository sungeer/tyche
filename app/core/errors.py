from starlette.responses import JSONResponse
from loguru import logger

from app.errors import BusinessError, AuthenticationError, PermissionDeniedError


# 业务失败
async def business_error(request, exc):
    # 前端通过 code 判断
    return JSONResponse(
        {'code': exc.code, 'msg': exc.msg, 'data': exc.data},
        status_code=200,
    )


# 请求错误
async def bad_request(request, exc):
    return JSONResponse(
        {'code': 400, 'msg': exc.msg, 'data': None},
        status_code=400,
    )


# 未登录
async def auth_error(request, exc):
    return JSONResponse(
        {'code': 401, 'msg': exc.msg, 'data': None},
        status_code=401,
    )


# 无权限
async def permission_error(request, exc):
    return JSONResponse(
        {'code': 403, 'msg': exc.msg, 'data': None},
        status_code=403,
    )


# 无法找到
async def not_found(request, exc):
    return JSONResponse(
        {'code': 404, 'msg': exc.msg, 'data': None},
        status_code=404,
    )


# 500
async def server_error(request, exc):
    """兜底处理
    数据库崩了 依赖超时 等 系统级异常
    监控在这里感知
    """
    logger.exception(
        f'unhandled exception on [{request.method}] [{request.url.path}]',
        exc_info=exc,
    )
    return JSONResponse(
        {'code': 500, 'msg': '服务器内部错误', 'data': None},
        status_code=500,
    )


exception_handlers = {
    400: bad_request,  # 整数键
    401: auth_error,
    403: permission_error,
    404: not_found,  # 处理主动声明为 404 的 HTTP 异常
    500: server_error,  # raise HTTPException(status_code=500, detail='something wrong') 触发
    BusinessError: business_error,  # 类键
    AuthenticationError: auth_error,
    PermissionDeniedError: permission_error,
    Exception: server_error,  # 处理所有没被预料到的 Python 异常
}
