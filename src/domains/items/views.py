from src.core.response import ok
from src.domains.items import service as item_service
from src.core.auth import login_required, permission_required
from src.utils import serial


@login_required
async def get_profile(request):
    user_id = request.user.user_id
    username = request.user.username
    roles = request.user.roles
    return ok()


@permission_required('order:create')
async def create_order(request):
    data = await request.json()  # dict
    user_id = request.user.user_id
    roles = request.user.roles

    order = await item_service.create_item(user_id, roles, data)
    data = {'order_id': order.id}
    return ok(data=data, msg='下单成功')
