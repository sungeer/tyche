from starlette.applications import Starlette

from app.core.events import lifespan
from app.core.handlers import exception_handlers
from app.middleware import middleware
from app.routes import routes

app = Starlette(
    routes=routes,
    middleware=middleware,
    exception_handlers=exception_handlers,
    lifespan=lifespan
)
