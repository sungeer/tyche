from src.domains.auth import repository as auth_repository
from src.core.db_registry import db
from src.utils import jose


async def auth_token(data: dict):
    user_name = data['user_name']
    password = data['password']

    with db.connect() as conn:
        db_user = await auth_repository.user_info(conn, user_name, password)

    subject = db_user['id']
    extra_data = {'role': 'admin'}

    jwt_token = jose.create_access_token(subject, extra_data)

    return jwt_token
