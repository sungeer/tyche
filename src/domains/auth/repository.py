from sqlalchemy import text


async def user_info(conn, user_name, password):
    sql = text('''
        SELECT
            id, name, age
        FROM
            user
        WHERE
            user_name = :user_name
            AND password = :password
    ''')
    parmas = {
        'user_name': user_name,
        'password': password,
    }
    result = conn.execute(sql, parmas)
    row = result.mappings().first()
    return dict(row) if row else None
