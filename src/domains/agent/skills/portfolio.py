"""
持仓相关 Skill 实现
对应持仓系统的 fin_portfolio* 系列表。
"""
from sqlalchemy import text


def query_customer_portfolio(params, conn):
    """
    查询客户持仓详情。
    返回持仓列表，每条包含产品信息和持仓量。
    """
    sql = text('''
        SELECT
            p.customer_id,
            p.product_id,
            f.product_name,
            f.product_type,
            f.risk_level,
            p.hold_amount,
            p.hold_nav,
            p.hold_value,
            p.cost_value,
            p.unrealized_pnl,
            p.position_date
        FROM
            fin_portfolio p
            JOIN fin_product f ON f.product_id = p.product_id
        WHERE
            p.customer_id = :customer_id
            AND p.deleted_at = 0
        ORDER BY
            p.hold_value DESC
    ''')
    result = conn.execute(sql, {'customer_id': params['customer_id']})
    rows = result.mappings().all()
    return {
        'customer_id': params['customer_id'],
        'positions': [dict(r) for r in rows],
        'total_value': sum(r['hold_value'] for r in rows) if rows else 0,
    }


def query_portfolio_risk_summary(params, conn):
    """
    查询客户持仓风险摘要（集中度、久期、风险等级分布等）。
    """
    # 查询风险等级分布
    sql_dist = text('''
        SELECT
            f.risk_level,
            COUNT(*) AS product_count,
            SUM(p.hold_value) AS total_value
        FROM
            fin_portfolio p
            JOIN fin_product f ON f.product_id = p.product_id
        WHERE
            p.customer_id = :customer_id
            AND p.deleted_at = 0
        GROUP BY
            f.risk_level
        ORDER BY
            f.risk_level
    ''')
    result_dist = conn.execute(sql_dist, {'customer_id': params['customer_id']})
    risk_distribution = [dict(r) for r in result_dist.mappings().all()]

    # 查询集中度（最大单只产品占比）
    sql_conc = text('''
        SELECT
            p.product_id,
            f.product_name,
            p.hold_value,
            p.hold_value / NULLIF(t.total, 0) AS concentration_ratio
        FROM
            fin_portfolio p
            JOIN fin_product f ON f.product_id = p.product_id
            JOIN (
                SELECT customer_id, SUM(hold_value) AS total
                FROM fin_portfolio
                WHERE customer_id = :customer_id AND deleted_at = 0
            ) t ON t.customer_id = p.customer_id
        WHERE
            p.customer_id = :customer_id
            AND p.deleted_at = 0
        ORDER BY
            concentration_ratio DESC
        LIMIT 3
    ''')
    result_conc = conn.execute(sql_conc, {'customer_id': params['customer_id']})
    top_holdings = [dict(r) for r in result_conc.mappings().all()]

    return {
        'customer_id': params['customer_id'],
        'risk_distribution': risk_distribution,
        'top_holdings': top_holdings,
    }
