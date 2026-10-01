import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 若存在
_dotenv_path = BASE_DIR / '.env'
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)


def _require(name: str) -> str:
    # 必填环境变量，缺失时启动即报错（fail fast）
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f'Missing required environment variables: {name}')
    return value


# 环境
_ENVIRONMENTS = ('development', 'testing', 'production')
ENVIRONMENT = _require('ENVIRONMENT')
if ENVIRONMENT not in _ENVIRONMENTS:
    raise ValueError(f'Invalid ENVIRONMENT: {ENVIRONMENT}, only allowed {sorted(_ENVIRONMENTS)}')

VERSION = '26.0930.0642'

# 日志
LOG_DIR = Path(os.getenv('LOG_DIR', default=str(BASE_DIR / 'logs')))

# Redis（任务队列后端）
REDIS_HOST = os.getenv('REDIS_HOST', default='127.0.0.1')
REDIS_PORT = int(os.getenv('REDIS_PORT', default='6379'))
REDIS_DB = int(os.getenv('REDIS_DB', default='0'))
