import math


def get_page_info(total, page=1, per_page=20):
    pages = math.ceil(total / per_page)
    next_num = page + 1 if page < pages else None
    has_next = page < pages
    prev_num = page - 1 if page > 1 else None
    has_prev = page > 1
    page_info = {
        'page': page,
        'per_page': per_page,  # 每页显示的记录数
        'pages': pages,  # 总页数
        'total': total,
        'next_num': next_num,
        'has_next': has_next,
        'prev_num': prev_num,
        'has_prev': has_prev
    }
    return page_info


async def query_by_filters(filters: dict | None = None):
    allowed_fields = {'id', 'name', 'age'}
    if filters:
        invalid = set(filters) - allowed_fields
        if invalid:
            raise ValueError(f'非法字段: {invalid}')

    where_clause = ''
    if filters:
        conditions = ' AND '.join(f'{field} = :{field}' for field in filters)
        where_clause = f'WHERE {conditions}'

    sql_str = f'''
        SELECT id, name, age
        FROM user
        {where_clause}
    '''

    async with engine.connect() as conn:
        result = await conn.execute(text(sql_str), filters or {})
        row = result.mappings().first()
        return dict(row) if row else None
