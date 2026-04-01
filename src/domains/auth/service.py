from src.core.exceptions import BusinessError
from src.core.codes import BizCode
from src.domains.auth import repository as auth_repository
from src.core.executor import db_threadpool
from src.utils.concurrency import run_in_threadpool
from src.core.db import engine
from src.utils import jose


async def auth_token(data: dict):
    user_name = data['user_name']
    password = data['password']

    def run_sync():
        with engine.connect() as conn:
            return auth_repository.user_info(conn, user_name, password)

    db_user = await run_in_threadpool(db_threadpool, run_sync)

    subject = db_user['id']
    extra_data = {'role': 'admin'}

    jwt_token = jose.create_access_token(subject, extra_data)

    return jwt_token
