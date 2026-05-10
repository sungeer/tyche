from contextlib import asynccontextmanager

from src.core.logger import setup_logger
from src.core.db_registry import db
from src.ai.llm_registry import llm_registry
from src.agents.game.graph_registry import graph_registry
from src.ai.milvus_registry import milvus_registry
from src.core.startup_state import startup_state


@asynccontextmanager
async def lifespan(app):
    setup_logger()

    db.init()
    startup_state.db_pool_ready = True

    llm_registry.init()
    await graph_registry.init()  # llm_registry 必须先行

    milvus_registry.init()

    startup_state.app_started = True

    yield

    await llm_registry.close()

    milvus_registry.close()

    await db.dispose()
