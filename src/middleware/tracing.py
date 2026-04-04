from src.core.context import run_id_var, new_run_id


class RunIdMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 跳过 lifespan 只在真实连接进来时才分配 run_id
        if scope['type'] in ('http', 'websocket'):
            run_id_var.set(new_run_id())  # 每个请求 统一分配 run_id
        await self.app(scope, receive, send)
