from src.core.response import ok
from src.domains.auth import service as auth_service
from src.utils import serial


# 获取 JWT Token
async def auth_token(request):
    body = serial.from_json(await request.body())
    jwt_token = await auth_service.auth_token(body)
    return ok(jwt_token)
