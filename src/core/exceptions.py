class AppError(Exception):
    """所有应用异常的基类"""
    pass


class BusinessError(AppError):
    """业务失败
    HTTP 200 + 非零 business code
    比如 库存不足 用户状态异常 参数业务校验失败
    """

    def __init__(self, code: int, msg: str, data=None):
        self.code = code
        self.msg = msg
        self.data = data


# 400
class BadRequestError(AppError):

    def __init__(self, msg='请求参数错误'):
        self.msg = msg


class AuthenticationError(AppError):
    """未登录
    Token 无效
    HTTP 401
    """

    def __init__(self, msg='未登录或登录已过期'):
        self.msg = msg


class ForbiddenError(AppError):
    """无操作权限
    HTTP 403
    """

    def __init__(self, msg='无权限执行此操作'):
        self.msg = msg


# JWT 已过期
class TokenExpiredError(AppError):

    def __init__(self, msg='JWT Token 已过期'):
        self.msg = msg


# JWT 非法或格式错误
class TokenInvalidError(AppError):

    def __init__(self, msg='JWT Token 非法或格式错误'):
        self.msg = msg
