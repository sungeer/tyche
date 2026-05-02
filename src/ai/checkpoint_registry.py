import aiomysql
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from src.core.config import settings


class _CheckpointRegistry:

    def __init__(self):
        self._pool = None
        self._checkpointer = None

    async def init(self):
        self._pool = await aiomysql.create_pool(  # type: ignore[misc]
            host=settings.db_host,
            port=settings.db_port,
            db=settings.db_name,
            user=settings.db_user,
            password=settings.db_pass,
            minsize=1,
            maxsize=5,  # AIOMySQLSaver 内部有锁导致该配置失效
            pool_recycle=1800,
            charset='utf8mb4',
            autocommit=True,  # LangGraph 指定
            connect_timeout=30,
        )

        self._checkpointer = AIOMySQLSaver(self._pool)

        await self._checkpointer.setup()  # 建表 幂等

    async def dispose(self):
        if self._pool is not None:
            await self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    def instance(self):
        if self._checkpointer is None:
            raise RuntimeError('checkpointer not initialized')
        return self._checkpointer


checkpoint_registry = _CheckpointRegistry()
