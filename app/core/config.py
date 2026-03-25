import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

with_debug = os.getenv('DEBUG') == '1'

is_win = sys.platform.startswith('win')

if with_debug or is_win:
    config_name = 'dev'
else:
    config_name = 'prod'

base_dir = Path(__file__).resolve().parent.parent.parent


class BaseConfig:
    log_path = base_dir / 'logs/app.log'


class DevConfig(BaseConfig):
    with_debug = 1
    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+asyncmy://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'


class ProdConfig(BaseConfig):
    with_debug = 0
    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+asyncmy://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'


config_map = {
    'dev': DevConfig,
    'prod': ProdConfig
}

settings = config_map.get(config_name, ProdConfig)
