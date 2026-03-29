import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

is_debug = os.getenv('DEBUG') == '1'

is_win = sys.platform.startswith('win')

if is_debug or is_win:
    config_name = 'dev'
else:
    config_name = 'prod'


class BaseConfig:
    base_dir = Path(__file__).resolve().parent.parent.parent

    log_path = base_dir / 'logs/app.log'

    jwt_algorithm = 'HS256'  # 加密算法
    jwt_access_token_expire_minutes = 30  # token 有效期 30s
    jwt_refresh_token_expire_days = 7


class DevConfig(BaseConfig):
    with_debug = 1

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    # 'openssl rand -hex 32'
    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+asyncmy://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'


class ProdConfig(BaseConfig):
    with_debug = 0

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+asyncmy://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'


config_map = {
    'dev': DevConfig,
    'prod': ProdConfig
}

settings = config_map.get(config_name, ProdConfig)
