import os
from pathlib import Path
from urllib.parse import quote_plus


class BaseConfig:
    base_dir = Path(__file__).resolve().parent.parent.parent

    # log_path = base_dir / 'logs/app.log'

    jwt_algorithm = 'HS256'  # 加密算法
    jwt_access_token_expire_minutes = 30  # 访问令牌有效期 30分钟
    jwt_refresh_token_expire_days = 7  # 刷新令牌有效期 7天


class DevConfig(BaseConfig):
    is_debug = 1

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    # 'openssl rand -hex 32'
    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+mysqldb://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'

    # 行内私有 LLM
    llm_base_url = 'http://llm.internal:8080'
    llm_api_key = 'dev-llm-key'

    # 行内私有 ChromaDB
    chroma_host = '127.0.0.1'
    chroma_port = 8000

    # 行内风控规则引擎
    risk_engine_url = 'http://risk-engine.internal'
    risk_engine_api_key = 'dev-risk-key'


class ProdConfig(BaseConfig):
    is_debug = 0

    origins = ['http://127.0.0.1:8080']  # cors 允许的来源 前端应用使用的端口

    jwt_secret_key = 'cb6103ca0209a5ae546ebea25acfafd5bcebe9ffbd37cb9ad58704c53fee99c1'

    db_passwd = quote_plus('admin')
    db_host = '127.0.0.1'
    db_url = f'mysql+mysqldb://root:{db_passwd}@{db_host}:3306/hostess?charset=utf8mb4'

    # 行内私有 LLM
    llm_base_url = os.getenv('LLM_BASE_URL', 'http://llm.internal:8080')
    llm_api_key = os.getenv('LLM_API_KEY', '')

    # 行内私有 ChromaDB
    chroma_host = os.getenv('CHROMA_HOST', '127.0.0.1')
    chroma_port = int(os.getenv('CHROMA_PORT', '8000'))

    # 行内风控规则引擎
    risk_engine_url = os.getenv('RISK_ENGINE_URL', 'http://risk-engine.internal')
    risk_engine_api_key = os.getenv('RISK_ENGINE_API_KEY', '')


config_map = {
    'dev': DevConfig,
    'prod': ProdConfig
}

is_debug = os.getenv('DEBUG') == '1'

config_name = 'dev' if is_debug else 'prod'

settings = config_map.get(config_name, ProdConfig)
