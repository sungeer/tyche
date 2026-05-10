from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core.db_registry import db
from src.core.startup_state import startup_state


@asynccontextmanager
async def lifespan(app):
    setup_logger()

    db.init()
    startup_state.db_pool_ready = True

    startup_state.app_started = True

    yield

    await db.dispose()
