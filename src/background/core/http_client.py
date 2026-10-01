from contextlib import suppress

import httpx2

# 统一暴露传输层错误，供上层捕获，避免各域直接依赖具体 HTTP 包
HTTPError = httpx2.HTTPError

# 供调用方按请求覆盖超时，不必直接依赖 httpx2
Timeout = httpx2.Timeout


class _HTTPClientHolder:

    def __init__(self):
        self._client = None

    def init(self):
        self._client = httpx2.Client(
            timeout=httpx2.Timeout(
                connect=5.0,
                read=30.0,
                write=5.0,
                pool=10.0
            ),
            limits=httpx2.Limits(
                max_connections=1000,
                keepalive_expiry=0.0,
            ),
            verify=False,
        )

    def get_client(self):
        if self._client is None:
            raise RuntimeError('HTTP client not initialized')
        return self._client

    def close(self):
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None


httpx = _HTTPClientHolder()
