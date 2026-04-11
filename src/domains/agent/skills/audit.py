"""
审计查询 Skill 实现
仅 COMPLIANCE 角色可调用。
"""
import json

from sqlalchemy import text


def query_audit_logs(params, conn):
    """
    查询审计日志。
    支持按 user_id、意图类别、时间范围过滤。
    """
    conditions = []
    query_params = {'limit': 100}

    if params.get('user_id'):
        conditions.append('user_id = :user_id')
        query_params['user_id'] = params['user_id']
    if params.get('intent_category'):
        conditions.append('intent_category = :intent_category')
        query_params['intent_category'] = params['intent_category']
    if params.get('start_date'):
        conditions.append('created_at >= :start_date')
        query_params['start_date'] = params['start_date']
    if params.get('end_date'):
        conditions.append('created_at <= :end_date')
        query_params['end_date'] = params['end_date']

    where_clause = f'WHERE {" AND ".join(conditions)}' if conditions else ''

    sql = text(f'''
        SELECT
            run_id, session_id, turn_id, user_id, operator_role,
            intent_category, intent_confidence, compliance_events,
            final_status, created_at
        FROM
            agent_audit_log
        {where_clause}
        ORDER BY
            id DESC
        LIMIT :limit
    ''')
    result = conn.execute(sql, query_params)
    rows = result.mappings().all()

    # 反序列化 JSON 字段
    logs = []
    for r in rows:
        item = dict(r)
        try:
            item['operator_role'] = json.loads(item['operator_role'])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            item['compliance_events'] = json.loads(item['compliance_events'])
        except (json.JSONDecodeError, TypeError):
            pass
        logs.append(item)

    return {'logs': logs, 'total': len(logs)}
