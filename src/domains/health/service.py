from src.core.exceptions import BusinessError
from src.core.codes import BizCode
from src.domains.health import repository
from src.core.db_registry import db


async def check_db_conn():
    async with db.connect() as conn:
        await repository.check_db_conn(conn)
    return None
