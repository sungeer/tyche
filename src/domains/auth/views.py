from src.core.response import ok
from src.domains.auth import service as auth_service


# 获取 JWT Token
async def auth_token(request):
    data = await request.json()  # dict
    jwt_token = await auth_service.auth_token(data)
    return ok(jwt_token)
