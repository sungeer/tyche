from starlette.applications import Starlette

from hostess.core.errors import exception_handlers
from app.core.events import lifespan
from hostess.core.routes import routes
from app.middleware import middleware

app = Starlette(
    routes=routes,
    middleware=middleware,
    exception_handlers=exception_handlers,
    lifespan=lifespan
)
