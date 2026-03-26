from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core import db


@asynccontextmanager
async def lifespan(app):
    setup_logger()
    yield
    await db.engine.dispose()
