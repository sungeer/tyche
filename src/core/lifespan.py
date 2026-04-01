from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core import db, executor


@asynccontextmanager
async def lifespan(app):
    setup_logger()
    yield
    executor.db_threadpool.shutdown(wait=True)
    executor.bio_threadpool.shutdown(wait=True)
    db.engine.dispose()
