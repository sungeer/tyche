from contextlib import suppress

from pymilvus import connections, Collection, utility
from src.core.config import settings


class _MilvusRegistry:

    def __init__(self):
        self._store = {}

    def init(self):
        connections.connect(
            host=settings.milvus_host,
            port=settings.milvus_port,
        )

        # settings.milvus_preload = ["constitution", "civil_law"]
        for name in settings.milvus_preload_collections:
            col = Collection(name)
            col.load()
            self._store[name] = col

    def close(self):
        for col in self._store.values():
            with suppress(Exception):
                col.release()
        self._store.clear()
        connections.disconnect('default')

    def get(self, name):
        if not self._store:
            raise RuntimeError('MilvusRegistry has not been initialized')
        if name not in self._store:
            raise KeyError(f'milvus [{name}] not registered, available: {list(self._store.keys())}')
        return self._store[name]

    def __getitem__(self, name):
        return self.get(name)


milvus_registry = _MilvusRegistry()
