from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core.db import db
from src.core.executor import db_threadpool, bio_threadpool
from src.ai.llm_registry import llm_registry


@asynccontextmanager
async def lifespan(app):
    setup_logger()

    db.init()

    llm_registry.init()

    yield

    db_threadpool.shutdown(wait=True)
    bio_threadpool.shutdown(wait=True)

    db.dispose()
