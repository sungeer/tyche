from src.core.exceptions import BusinessError
from src.core.codes import BizCode


async def create_order(user_id: int, roles: list[str], data: dict):
    stock = await stock_repository.get_stock(data['product_id'])
    if stock < data['quantity']:
        raise BusinessError(BizCode.STOCK_INSUFFICIENT, '库存不足，请减少购买数量')

    # 数据库 操作交给 repository 层，它只抛系统异常，不抛业务异常
    order = await order_repository.insert(user_id, data)
    return order
