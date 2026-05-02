from src.ai.checkpoint_registry import checkpoint_registry
from src.agents.game.graph import build_game_graph


class _GraphRegistry:

    def __init__(self):
        self._store = {}
        self._checkpointer_cm = None  # 保存上下文管理器，用于关闭时清理

    async def init(self):
        checkpointer = checkpoint_registry.instance()

        self._store = {
            'game': build_game_graph(checkpointer),
        }

    def get(self, name):
        if not self._store:
            raise RuntimeError('graph registry has not been initialized')
        if name not in self._store:
            raise KeyError(f'graph [{name}] not registered, available: {list(self._store.keys())}')
        return self._store[name]

    # registry['game']
    def __getitem__(self, name):
        return self.get(name)


graph_registry = _GraphRegistry()
