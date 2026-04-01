from starlette.authentication import requires

from src.core.response import ok
from src.domains.items import service as item_service
from src.utils import serial


@requires('authenticated', status_code=401)  # 需要登录
async def get_profile(request):
    user_id = request.user.user_id
    username = request.user.username
    roles = request.user.roles
    return ok()


@requires('order:create')  # 没有这个 scope 直接 403
async def create_order(request):
    # body = await request.json()
    body = serial.from_json(await request.body())
    user_id = request.user.user_id
    roles = request.user.roles  # 从 JWTUser 取
    scopes = request.auth.scopes  # 从 AuthCredentials 取 和 roles 内容一样

    order = await item_service.create_item(user_id, roles, body)
    data = {'order_id': order.id}
    return ok(data=data, msg='下单成功')
