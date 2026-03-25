class AppException(Exception):
    """所有应用异常的基类"""
    pass


class BusinessError(AppException):
    """业务失败
    HTTP 200 + 非零 business code
    比如 库存不足 用户状态异常 参数业务校验失败
    """

    def __init__(self, code: int, msg: str, data=None):
        self.code = code
        self.msg = msg
        self.data = data


class AuthenticationError(AppException):
    """未登录
    Token 无效
    HTTP 401
    """

    def __init__(self, msg: str = '未登录或登录已过期'):
        self.msg = msg


class PermissionDeniedError(AppException):
    """无操作权限
    HTTP 403
    """

    def __init__(self, msg: str = '无权限执行此操作'):
        self.msg = msg


# 业务 code 常量
class BizCode:
    OK = 0
    PARAM_ERROR = 1001
    STOCK_INSUFFICIENT = 2001
    USER_DISABLED = 2002
    ORDER_EXPIRED = 2003
