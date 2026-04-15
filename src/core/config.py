import os
from pathlib import Path
from urllib.parse import quote_plus


class BaseConfig:
    base_dir = Path(__file__).resolve().parent.parent.parent

    # log_path = base_dir / 'logs/app.log'

    jwt_algorithm = 'HS256'  # 加密算法
    jwt_access_token_expire_minutes = 30  # 访问令牌有效期 30分钟
    jwt_refresh_token_expire_days = 7  # 刷新令牌有效期 7天

    # 其他配置
    max_history_length = 100


class DevConfig(BaseConfig):
    is_debug = 1

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    # 'openssl rand -hex 32'
    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+mysqldb://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'

    # LLM 配置
    default_model = 'gpt-3.5-turbo'
    default_provider = 'openai'
    temperature = 0.7  # float
    max_tokens = None  # int


class ProdConfig(BaseConfig):
    is_debug = 0

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+mysqldb://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'

    # LLM 配置
    default_model = 'gpt-3.5-turbo'
    default_provider = 'openai'
    temperature = 0.7  # float
    max_tokens = None  # int


config_map = {
    'dev': DevConfig,
    'prod': ProdConfig
}

is_debug = os.getenv('DEBUG') == '1'

config_name = 'dev' if is_debug else 'prod'

settings = config_map.get(config_name, ProdConfig)
