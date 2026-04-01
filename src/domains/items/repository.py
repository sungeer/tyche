from sqlalchemy import text


def query_one(conn, user_id):
    sql = text('''
        SELECT
            id, name, age
        FROM
            user
        WHERE
            id = :id
    ''')
    result = conn.execute(sql, {'id': user_id})
    row = result.mappings().first()
    return dict(row) if row else None
