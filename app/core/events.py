from contextlib import asynccontextmanager

from app.core.logger import setup_logger
from app import db


@asynccontextmanager
async def lifespan(app):
    setup_logger()
    yield
    await db.engine.dispose()
