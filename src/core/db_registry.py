from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings


class _EngineHolder:

    def __init__(self):
        self._engine = None

    def init(self):
        self._engine = create_async_engine(
            settings.db_url,
            echo=False,  # 不打印SQL语句
            pool_size=5,  # 空闲连接 上限
            max_overflow=7,  # 高峰额外最多再开 10 条
            pool_timeout=30,  # 取连接等待 30s 失败就报错
            pool_recycle=1800,  # 回收重连
            pool_pre_ping=True,  # 避免拿到失效连接
            pool_use_lifo=True,  # 复用热连接
        )

    def connect(self):
        if self._engine is None:
            raise RuntimeError('db engine not initialized')
        return self._engine.connect()

    def begin(self):
        if self._engine is None:
            raise RuntimeError('db engine not initialized')
        return self._engine.begin()

    async def dispose(self):
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

db = _EngineHolder()
