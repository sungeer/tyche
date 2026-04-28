from src.ai.game_graph.graph import build_game_graph


class _GraphRegistry:

    def __init__(self):
        self._store = {}

    def init(self):
        self._store = {
            'game': build_game_graph(),
        }

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
