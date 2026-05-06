from urllib.parse import urlparse, unquote_plus, parse_qs

import pymysql
from dbutils.pooled_db import PooledDB

from src.core.config import settings


def _parse_db_url(url: str) -> dict:
    # 解析 SQLAlchemy 格式的 URL，提取 pymysql 所需的独立参数
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 3306,
        'user': parsed.username,
        'password': unquote_plus(parsed.password or ''),
        'database': parsed.path.lstrip('/'),
        'charset': query.get('charset', ['utf8mb4'])[0],
    }


class _PoolHolder:

    def __init__(self):
        self._pool = None

    def init(self):
        params = _parse_db_url(settings.db_url)
        self._pool = PooledDB(
            creator=pymysql,
            maxconnections=12,  # 空闲+高峰上限（对应原 pool_size=5 + max_overflow=7）
            mincached=5,        # 启动时预建的空闲连接数
            maxcached=5,        # 空闲连接上限
            blocking=True,      # 连接用尽时阻塞等待，不抛异常（对应原 pool_timeout）
            ping=1,             # 取连接前 ping，避免拿到失效连接（对应原 pool_pre_ping）
            cursorclass=pymysql.cursors.DictCursor,
            host=params['host'],
            port=params['port'],
            user=params['user'],
            password=params['password'],
            database=params['database'],
            charset=params['charset'],
        )

    def connect(self):
        if self._pool is None:
            raise RuntimeError('db pool not initialized')
        return self._pool.connection()

    def dispose(self):
        if self._pool is not None:
            self._pool.close()
            self._pool = None


db = _PoolHolder()
