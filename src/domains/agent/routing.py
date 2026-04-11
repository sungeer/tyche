# 意图 → 所需权限映射
# 用于 Node2 权限检查
INTENT_PERMISSION_MAP = {
    'product_query':       'product:read',
    'product_compare':     'product:read',
    'portfolio_analysis':  'portfolio:read',
    'risk_assessment':     'risk:read',
    'redemption_initiate': 'redemption:initiate',
    'audit_query':         'audit:read',
    # 以下意图无需权限检查（在 Node1 已短路）
    'small_talk':          None,
    'out_of_scope':        None,
    'ambiguous':           None,
}

# 意图 → Skill ID 列表映射（有序）
# 此处定义的是意图默认触发的 Skill 列表
# 实际入参由 Node2 从 intent.entities 自动映射
INTENT_SKILL_MAP = {
    'product_query': [
        'query_product_detail',
        'query_product_nav_history',
    ],
    'product_compare': [
        'query_product_detail',
        'query_product_risk_metrics',
    ],
    'portfolio_analysis': [
        'query_customer_portfolio',
        'query_portfolio_risk_summary',
    ],
    'risk_assessment': [
        'query_customer_portfolio',     # run_stress_test 的 portfolio_snapshot 由此注入
        'query_portfolio_risk_summary',
        'run_stress_test',              # depends_on: query_customer_portfolio
    ],
    'redemption_initiate': [
        'query_product_detail',     # 先查产品，供审核人参考
        'query_redemption_quota',   # 查可赎回额度
        # 实际赎回 Skill 在人工审核通过后执行
    ],
    'audit_query': [
        'query_audit_logs',
    ],
}

# 人工审核触发规则
# Node2 按顺序逐条检查，命中第一条即触发
HUMAN_REVIEW_RULES = [
    {
        'rule_id': 'redemption_large_amount',
        'description': '赎回金额 >= 50 万元',
        'assign_to_role': 'COMPLIANCE',
        'sla_hours': 2,
    },
    {
        'rule_id': 'risk_waiver_operation',
        'description': '客户签署风险承担声明后的越级产品操作',
        'assign_to_role': 'COMPLIANCE',
        'sla_hours': 8,             # 1 个工作日
    },
    {
        'rule_id': 'frequent_portfolio_access',
        'description': '同一顾问同日内第 3 次及以上访问同一客户全部持仓',
        'assign_to_role': 'RISK_OFFICER',
        'sla_hours': 4,
    },
]

# 按 rule_id 快速查找审核规则，避免硬编码下标
REVIEW_RULE_MAP = {r['rule_id']: r for r in HUMAN_REVIEW_RULES}
