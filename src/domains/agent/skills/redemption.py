"""
赎回相关 Skill 实现
赎回申请属于写操作，需人工审核通过后才会调用 initiate_redemption。
"""
from sqlalchemy import text


def query_redemption_quota(params, conn):
    """查询产品可赎回额度"""
    sql = text('''
        SELECT
            product_id,
            customer_id,
            available_amount,
            max_single_redemption,
            redemption_fee_rate,
            settlement_days,
            calc_date
        FROM
            fin_redemption_quota
        WHERE
            product_id = :product_id
            AND customer_id = :customer_id
            AND deleted_at = 0
    ''')
    result = conn.execute(sql, {
        'product_id': params['product_id'],
        'customer_id': params['customer_id'],
    })
    row = result.mappings().first()
    return dict(row) if row else None


def initiate_redemption(params, conn):
    """
    发起赎回申请（写操作）。
    幂等保证：先按 idempotency_key 查重，已存在则直接返回原记录。
    """
    idempotency_key = params.get('idempotency_key', '')

    # 幂等检查：同一 idempotency_key 只执行一次
    if idempotency_key:
        sql_check = text('''
            SELECT
                id, redemption_no, status
            FROM
                fin_redemption_order
            WHERE
                idempotency_key = :idempotency_key
        ''')
        result = conn.execute(sql_check, {'idempotency_key': idempotency_key})
        existing = result.mappings().first()
        if existing:
            return {'idempotent': True, 'redemption_no': existing['redemption_no']}

    # 生成赎回单号（实际应使用分布式 ID 服务）
    sql_insert = text('''
        INSERT INTO fin_redemption_order (
            customer_id, product_id, amount, status,
            idempotency_key, created_at
        )
        VALUES (
            :customer_id, :product_id, :amount, 'pending',
            :idempotency_key, NOW(3)
        )
    ''')
    conn.execute(sql_insert, {
        'customer_id': params['customer_id'],
        'product_id': params['product_id'],
        'amount': params['amount'],
        'idempotency_key': idempotency_key,
    })

    # 查询刚插入的记录
    sql_fetch = text('''
        SELECT id, idempotency_key, status
        FROM fin_redemption_order
        WHERE idempotency_key = :idempotency_key
    ''')
    result = conn.execute(sql_fetch, {'idempotency_key': idempotency_key})
    row = result.mappings().first()
    return {
        'idempotent': False,
        'redemption_id': row['id'] if row else None,
    }
