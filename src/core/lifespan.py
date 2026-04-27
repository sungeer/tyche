from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core.db import db
from src.core.executor import db_threadpool, bio_threadpool
from src.ai.core import llm_registry, graph_registry


@asynccontextmanager
async def lifespan(app):
    setup_logger()

    db.init()

    llm_registry.init()
    graph_registry.init()  # 无需关闭 但 llm_registry 必须先行

    yield

    db_threadpool.shutdown(wait=True)
    bio_threadpool.shutdown(wait=True)

    await llm_registry.close()

    db.dispose()
