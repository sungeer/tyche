from contextlib import asynccontextmanager

from app import db
from app.core.logger import setup_logger


@asynccontextmanager
async def lifespan(app):
    setup_logger()
    yield
    await db.engine.dispose()
