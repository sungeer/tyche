from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from src.core.config import settings
from src.agents.game.graph import build_game_graph


class _GraphRegistry:

    def __init__(self):
        self._store = {}
        self._checkpointer_cm = None  # 保存上下文管理器，用于关闭时清理

    async def init(self):
        # mysql+aiomysql://... -> mysql://...（去掉驱动标识和查询参数）
        checkpoint_url = settings.db_url.replace('+aiomysql', '').split('?')[0]

        self._checkpointer_cm = AIOMySQLSaver.from_conn_string(checkpoint_url)
        checkpointer = await self._checkpointer_cm.__aenter__()
        await checkpointer.setup()  # 建表 幂等

        self._store = {
            'game': build_game_graph(checkpointer),
        }

    async def dispose(self):
        if self._checkpointer_cm is not None:
            await self._checkpointer_cm.__aexit__(None, None, None)
            self._checkpointer_cm = None

    def get(self, name):
        if not self._store:
            raise RuntimeError('GraphRegistry has not been initialized')
        if name not in self._store:
            raise KeyError(f'graph [{name}] not registered, available: {list(self._store.keys())}')
        return self._store[name]

    # registry['game']
    def __getitem__(self, name):
        return self.get(name)


graph_registry = _GraphRegistry()
