def query_one(conn, user_id: int):
    sql = '''
        SELECT
            id, name, age
        FROM
            user
        WHERE
            id = %s
    '''
    with conn.cursor() as cursor:
        cursor.execute(sql, (user_id,))
        return cursor.fetchone()


def insert(conn, user_id: int, data: dict):
    pass
