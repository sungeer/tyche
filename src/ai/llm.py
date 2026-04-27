import httpx
from langchain_openai import ChatOpenAI
from openai import http_client, api_key


class _LLMRegistry:

    def __init__(self):
        self._client = None
        self._store = {}

    def init(self):
        self._client = httpx.AsyncClient(verify=False)  # 内网代理 禁用 SSL

        self._store = {
            'common': ChatOpenAI(
                model='Qwen3-A22B',
                base_url='http://127.0.0.1:7788/v1',
                api_key='sk_zaq1xsw2cde',  # noqa
                streaming=True,
                http_async_client=self._client,
            ),
            'think': ChatOpenAI(
                model='Qwen3-30B',
                base_url='http://127.0.0.1:6699/v1',
                api_key='sk_zaq1xsw2cde',  # noqa
                streaming=True,
                http_async_client=self._client,
            ),
        }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self._store.clear()

    def get(self, name):
        if not self._store:
            raise RuntimeError('LLMRegistry has not been initialized')
        if name not in self._store:
            raise KeyError(f'llm [{name}] not registered, available: {list(self._store.keys())}')
        return self._store[name]

    # registry['common']
    def __getitem__(self, name):
        return self.get(name)


llm_registry = _LLMRegistry()
