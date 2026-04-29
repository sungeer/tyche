from sqlalchemy import text


async def check_db_conn(conn):
    sql = text('SELECT 1')
    await conn.execute(sql)
    return None
