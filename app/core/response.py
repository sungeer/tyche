import datetime
import decimal

import orjson
from starlette.responses import JSONResponse


def json_encoder(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    elif isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(obj, datetime.date):
        return obj.strftime('%Y-%m-%d')
    raise TypeError(f'不支持的类型: {type(obj)}')


class Response(JSONResponse):
    def render(self, content) -> bytes:
        # content is Any
        return orjson.dumps(content, default=json_encoder)


# 成功响应
def ok(data=None, msg='success'):
    return Response({
        'code': 0,
        'msg': msg,
        'data': data,
    })


# 业务失败响应
def fail(code: int, msg: str, data=None):
    """业务失败响应
    HTTP 状态码仍为 200
    通常不直接调用，而是通过 raise BusinessError 触发
    """
    return Response({
        'code': code,
        'msg': msg,
        'data': data,
    }, status_code=200)
