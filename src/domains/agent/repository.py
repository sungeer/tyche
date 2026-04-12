import json
from datetime import datetime, timezone

from sqlalchemy import text


def _now_utc():
    """返回 UTC 当前时间字符串，毫秒精度"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


# ==================== 会话 ====================

def create_session(conn, session_id, user_id):
    """创建新会话"""
    now = _now_utc()
    sql = text('''
        INSERT INTO agent_session (
            session_id, user_id, status, turn_count,
            last_active_at, created_at, updated_at, deleted_at
        )
        VALUES (
            :session_id, :user_id, 'active', 0,
            :now, :now, :now, 0
        )
    ''')
    conn.execute(sql, {'session_id': session_id, 'user_id': user_id, 'now': now})


# 按 session_id 查询会话
def get_session_by_id(conn, session_id):
    sql = text('''
        SELECT
            id, session_id, user_id, status, turn_count,
            last_active_at, created_at, updated_at
        FROM
            agent_session
        WHERE
            session_id = :session_id
            AND deleted_at = 0
    ''')
    result = conn.execute(sql, {'session_id': session_id})
    row = result.mappings().first()
    return dict(row) if row else None


def update_session_active(conn, session_id):
    """更新会话最后活跃时间并累加轮次数"""
    now = _now_utc()
    sql = text('''
        UPDATE agent_session
        SET
            last_active_at = :now,
            turn_count = turn_count + 1,
            updated_at = :now
        WHERE
            session_id = :session_id
    ''')
    conn.execute(sql, {'session_id': session_id, 'now': now})


def close_session(conn, session_id):
    """关闭会话（超时或用户主动清除）"""
    now = _now_utc()
    sql = text('''
        UPDATE agent_session
        SET
            status = 'closed',
            updated_at = :now
        WHERE
            session_id = :session_id
    ''')
    conn.execute(sql, {'session_id': session_id, 'now': now})


# ==================== 消息 ====================

# 查询 指定轮次 的助手 回复消息
def get_assistant_message_by_turn_id(conn, turn_id):
    sql = text('''
        SELECT
            id, session_id, turn_id, role, content, created_at
        FROM
            agent_message
        WHERE
            turn_id = :turn_id
            AND role = 'assistant'
        LIMIT 1
    ''')
    result = conn.execute(sql, {'turn_id': turn_id})
    row = result.mappings().first()
    return dict(row) if row else None


def get_messages_by_session(conn, session_id, limit=40):
    """
    获取最近 limit 条消息（最多 40 条即 20 轮）。
    按 id 倒序取后正序返回，保证历史顺序正确。
    """
    sql = text('''
        SELECT
            id, session_id, turn_id, role, content, created_at
        FROM
            agent_message
        WHERE
            session_id = :session_id
        ORDER BY
            id DESC
        LIMIT :limit
    ''')
    result = conn.execute(sql, {'session_id': session_id, 'limit': limit})
    rows = list(reversed(result.mappings().all()))
    return [dict(r) for r in rows]


def insert_message(conn, session_id, turn_id, role, content):
    """插入一条对话消息"""
    now = _now_utc()
    sql = text('''
        INSERT INTO agent_message (
            session_id, turn_id, role, content, created_at
        )
        VALUES (
            :session_id, :turn_id, :role, :content, :now
        )
    ''')
    conn.execute(sql, {
        'session_id': session_id,
        'turn_id': turn_id,
        'role': role,
        'content': content,
        'now': now,
    })


# ==================== 审计日志 ====================

def insert_audit_log(conn, record):
    """
    插入审计日志。
    审计日志只插入不更新（防篡改）。
    """
    sql = text('''
        INSERT INTO agent_audit_log (
            run_id, session_id, turn_id, user_id, operator_role,
            intent_category, intent_confidence, skills_called,
            compliance_events, node_durations, llm_token_usage,
            final_status, content_hash, created_at
        )
        VALUES (
            :run_id, :session_id, :turn_id, :user_id, :operator_role,
            :intent_category, :intent_confidence, :skills_called,
            :compliance_events, :node_durations, :llm_token_usage,
            :final_status, :content_hash, :created_at
        )
    ''')
    conn.execute(sql, {
        'run_id': record['run_id'],
        'session_id': record['session_id'],
        'turn_id': record['turn_id'],
        'user_id': record['user_id'],
        'operator_role': json.dumps(record['operator_role'], ensure_ascii=False),
        'intent_category': record['intent_category'],
        'intent_confidence': record['intent_confidence'],
        'skills_called': json.dumps(record['skills_called'], ensure_ascii=False),
        'compliance_events': json.dumps(record['compliance_events'], ensure_ascii=False),
        'node_durations': json.dumps(record['node_durations'], ensure_ascii=False),
        'llm_token_usage': json.dumps(record['llm_token_usage'], ensure_ascii=False),
        'final_status': record['final_status'],
        'content_hash': record['content_hash'],
        'created_at': record['created_at'],
    })


def count_portfolio_access_today(conn, user_id, day_start, day_end):
    """
    统计指定顾问当日调用 query_customer_portfolio 的次数。
    用于触发频繁访问审核规则（同日 >= 3 次触发）。
    注：因 customer_id 未单独落库，统计当日全量持仓访问次数（保守近似）。
    """
    sql = text('''
        SELECT COUNT(*) AS cnt
        FROM
            agent_audit_log
        WHERE
            user_id = :user_id
            AND created_at >= :day_start
            AND created_at < :day_end
            AND JSON_SEARCH(
                    skills_called, 'one',
                    'query_customer_portfolio',
                    NULL, '$[*].skill_id'
                ) IS NOT NULL
    ''')
    result = conn.execute(sql, {
        'user_id': user_id,
        'day_start': day_start,
        'day_end': day_end,
    })
    row = result.mappings().first()
    return row['cnt'] if row else 0


def get_recent_audit_logs_for_metrics(conn, since_dt, limit=1000):
    """获取近期审计日志，供 metrics 接口聚合计算，只取必要字段"""
    sql = text('''
        SELECT
            final_status,
            intent_category,
            skills_called,
            node_durations
        FROM
            agent_audit_log
        WHERE
            created_at >= :since_dt
        ORDER BY
            id DESC
        LIMIT :limit
    ''')
    result = conn.execute(sql, {'since_dt': since_dt, 'limit': limit})
    return [dict(r) for r in result.mappings().all()]


def get_audit_logs(conn, user_id=None, intent_category=None,
                   start_date=None, end_date=None, limit=100):
    """查询审计日志（供 COMPLIANCE 角色使用）"""
    conditions = []
    params = {'limit': limit}

    if user_id:
        conditions.append('user_id = :user_id')
        params['user_id'] = user_id
    if intent_category:
        conditions.append('intent_category = :intent_category')
        params['intent_category'] = intent_category
    if start_date:
        conditions.append('created_at >= :start_date')
        params['start_date'] = start_date
    if end_date:
        conditions.append('created_at <= :end_date')
        params['end_date'] = end_date

    where_clause = f'WHERE {" AND ".join(conditions)}' if conditions else ''

    sql = text(f'''
        SELECT
            id, run_id, session_id, turn_id, user_id, operator_role,
            intent_category, intent_confidence, skills_called,
            compliance_events, node_durations, llm_token_usage,
            final_status, content_hash, created_at
        FROM
            agent_audit_log
        {where_clause}
        ORDER BY
            id DESC
        LIMIT :limit
    ''')
    result = conn.execute(sql, params)
    return [dict(r) for r in result.mappings().all()]


# ==================== 人工审核任务 ====================

def insert_review_task(conn, task):
    """创建人工审核任务"""
    now = _now_utc()
    sql = text('''
        INSERT INTO agent_review_task (
            task_id, turn_id, user_id, assigned_role, assigned_to,
            trigger_rule, trigger_detail, status, reviewer_note,
            sla_deadline, created_at, updated_at
        )
        VALUES (
            :task_id, :turn_id, :user_id, :assigned_role, 0,
            :trigger_rule, :trigger_detail, 'pending', '',
            :sla_deadline, :now, :now
        )
    ''')
    conn.execute(sql, {
        'task_id': task['task_id'],
        'turn_id': task['turn_id'],
        'user_id': task['user_id'],
        'assigned_role': task['assigned_role'],
        'trigger_rule': task['trigger_rule'],
        'trigger_detail': task['trigger_detail'],
        'sla_deadline': task['sla_deadline'],
        'now': now,
    })


# 按 task_id 查询 审核任务
def get_review_task(conn, task_id):
    sql = text('''
        SELECT
            id, task_id, turn_id, user_id, assigned_role, assigned_to,
            trigger_rule, trigger_detail, status, reviewer_note,
            sla_deadline, reviewed_at, created_at, updated_at
        FROM
            agent_review_task
        WHERE
            task_id = :task_id
    ''')
    result = conn.execute(sql, {'task_id': task_id})
    row = result.mappings().first()
    return dict(row) if row else None


def get_pending_review_tasks_by_role(conn, role, limit=50):
    """查询指定角色的待处理审核任务，按 SLA 截止时间升序"""
    sql = text('''
        SELECT
            id, task_id, turn_id, user_id, assigned_role, assigned_to,
            trigger_rule, trigger_detail, status, reviewer_note,
            sla_deadline, reviewed_at, created_at, updated_at
        FROM
            agent_review_task
        WHERE
            assigned_role = :role
            AND status = 'pending'
        ORDER BY
            sla_deadline ASC
        LIMIT :limit
    ''')
    result = conn.execute(sql, {'role': role, 'limit': limit})
    return [dict(r) for r in result.mappings().all()]


def update_review_task_status(conn, task_id, status, reviewer_note, reviewed_at=None):
    """更新审核任务状态"""
    now = _now_utc()
    sql = text('''
        UPDATE agent_review_task
        SET
            status = :status,
            reviewer_note = :reviewer_note,
            reviewed_at = :reviewed_at,
            updated_at = :now
        WHERE
            task_id = :task_id
    ''')
    conn.execute(sql, {
        'task_id': task_id,
        'status': status,
        'reviewer_note': reviewer_note,
        'reviewed_at': reviewed_at or now,
        'now': now,
    })


# ==================== State 快照 ====================

def insert_state_snapshot(conn, task_id, state_json):
    """保存 AgentState 快照（人工审核恢复用）"""
    now = _now_utc()
    sql = text('''
        INSERT INTO agent_state_snapshot (
            task_id, state_json, created_at
        )
        VALUES (
            :task_id, :state_json, :now
        )
    ''')
    conn.execute(sql, {'task_id': task_id, 'state_json': state_json, 'now': now})


def get_state_snapshot(conn, task_id):
    """读取 AgentState 快照"""
    sql = text('''
        SELECT
            task_id, state_json, created_at
        FROM
            agent_state_snapshot
        WHERE
            task_id = :task_id
    ''')
    result = conn.execute(sql, {'task_id': task_id})
    row = result.mappings().first()
    return dict(row) if row else None
