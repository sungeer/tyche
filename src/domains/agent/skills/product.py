"""
产品相关 Skill 实现
对应银行产品库的 fin_product* 系列表。
"""
from sqlalchemy import text


def query_product_detail(params, conn):
    """
    查询单个理财产品基本信息。
    入参支持 product_id 或 product_name（二选一）。
    """
    if 'product_id' in params:
        sql = text('''
            SELECT
                product_id, product_name, product_type, risk_level,
                nav, nav_date, yield_7d, yield_1y, scale, manager,
                purchase_min, redemption_fee, status
            FROM
                fin_product
            WHERE
                product_id = :product_id
                AND deleted_at = 0
        ''')
        result = conn.execute(sql, {'product_id': params['product_id']})
        row = result.mappings().first()
        return dict(row) if row else None
    else:
        sql = text('''
            SELECT
                product_id, product_name, product_type, risk_level,
                nav, nav_date, yield_7d, yield_1y, scale, manager,
                purchase_min, redemption_fee, status
            FROM
                fin_product
            WHERE
                product_name LIKE :product_name
                AND deleted_at = 0
            LIMIT 5
        ''')
        result = conn.execute(sql, {'product_name': f'%{params["product_name"]}%'})
        rows = result.mappings().all()
        return [dict(r) for r in rows]


def query_product_nav_history(params, conn):
    """查询产品净值历史走势"""
    query_params = {'product_id': params['product_id']}
    date_filter = ''

    if params.get('start_date'):
        date_filter += ' AND nav_date >= :start_date'
        query_params['start_date'] = params['start_date']
    if params.get('end_date'):
        date_filter += ' AND nav_date <= :end_date'
        query_params['end_date'] = params['end_date']

    sql = text(f'''
        SELECT
            nav_date, nav, daily_return
        FROM
            fin_product_nav_history
        WHERE
            product_id = :product_id
            {date_filter}
        ORDER BY
            nav_date DESC
        LIMIT 365
    ''')
    result = conn.execute(sql, query_params)
    rows = list(reversed(result.mappings().all()))
    return {
        'product_id': params['product_id'],
        'history': [dict(r) for r in rows],
    }


def query_product_risk_metrics(params, conn):
    """查询产品风险指标（波动率、最大回撤、夏普比率等）"""
    sql = text('''
        SELECT
            product_id, volatility_1y, max_drawdown_1y,
            sharpe_ratio, beta, calc_date
        FROM
            fin_product_risk_metrics
        WHERE
            product_id = :product_id
        ORDER BY
            calc_date DESC
        LIMIT 1
    ''')
    result = conn.execute(sql, {'product_id': params['product_id']})
    row = result.mappings().first()
    return dict(row) if row else None
