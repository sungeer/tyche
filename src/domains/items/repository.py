from sqlalchemy import text


async def query_one(conn, user_id):
    sql = text('''
        SELECT
            id, name, age
        FROM
            user
        WHERE
            id = :id
    ''')
    result = await conn.execute(sql, {'id': user_id})
    row = result.mappings().first()
    return dict(row) if row else None
