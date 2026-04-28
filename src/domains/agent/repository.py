from sqlalchemy import text


# 查询 话题
async def get_conversation_id(conn, session_id: str) -> int | None:
    sql = text('''
        SELECT
            id
        FROM
            conversations
        WHERE
            session_id = :session_id
    ''')
    result = await conn.execute(sql, {'session_id': session_id})
    row = result.mappings().first()
    return row['id'] if row else None


# 创建 新话题
async def create_conversation(conn, user_id: int, session_id: str) -> int:
    sql = text('''
        INSERT INTO conversations (user_id, session_id, title)
        VALUES (:user_id, :session_id, '新对话')
    ''')
    result = await conn.execute(sql, {'user_id': user_id, 'session_id': session_id})
    return result.lastrowid


# 查询 指定话题下的消息
async def get_messages(conn, conversation_id: int) -> list[dict]:
    sql = text('''
        SELECT
            role, content
        FROM
            messages
        WHERE
            conversation_id = :conversation_id
        ORDER BY id
    ''')
    result = await conn.execute(sql, {'conversation_id': conversation_id})
    return [dict(r) for r in result.mappings().all()]


async def insert_message(conn, conversation_id: int, role: str, content: str) -> None:
    sql = text('''
        INSERT INTO messages (conversation_id, role, content, status)
        VALUES (:conversation_id, :role, :content, 'completed')
    ''')
    await conn.execute(sql, {'conversation_id': conversation_id, 'role': role, 'content': content})
