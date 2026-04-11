# Skill 注册表
# 应用启动时一次性加载，运行时只读
# 每个 Skill 定义了：描述、所需权限、参数 Schema、依赖关系、超时、降级策略

SKILL_REGISTRY = {

    'query_product_detail': {
        'description': '查询单个理财产品的基本信息（净值、收益率、风险等级、规模等）',
        'required_permission': 'product:read',
        'params_schema': {
            'type': 'object',
            'properties': {
                'product_id': {'type': 'string'},
                'product_name': {'type': 'string'},
            },
            'oneOf': [
                {'required': ['product_id']},
                {'required': ['product_name']},
            ],
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'query_product_nav_history': {
        'description': '查询产品净值历史走势',
        'required_permission': 'product:read',
        'params_schema': {
            'type': 'object',
            'required': ['product_id'],
            'properties': {
                'product_id': {'type': 'string'},
                'start_date': {'type': 'string'},
                'end_date': {'type': 'string'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'query_product_risk_metrics': {
        'description': '查询产品风险指标（波动率、最大回撤等）',
        'required_permission': 'product:read',
        'params_schema': {
            'type': 'object',
            'required': ['product_id'],
            'properties': {
                'product_id': {'type': 'string'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'query_customer_portfolio': {
        'description': '查询客户持仓详情',
        'required_permission': 'portfolio:read',
        'params_schema': {
            'type': 'object',
            'required': ['customer_id'],
            'properties': {
                'customer_id': {'type': 'integer'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'query_portfolio_risk_summary': {
        'description': '查询客户持仓风险摘要（集中度、久期等）',
        'required_permission': 'portfolio:read',
        'params_schema': {
            'type': 'object',
            'required': ['customer_id'],
            'properties': {
                'customer_id': {'type': 'integer'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'run_stress_test': {
        'description': '对客户当前持仓做压力测试（需先获取持仓数据）',
        'required_permission': 'risk:read',
        'params_schema': {
            'type': 'object',
            'required': ['customer_id', 'portfolio_snapshot'],
            'properties': {
                'customer_id': {'type': 'integer'},
                'portfolio_snapshot': {'type': 'object'},
                'scenario': {
                    'type': 'string',
                    'enum': ['rate_up_100bp', 'market_crash_30pct'],
                },
            },
        },
        'depends_on': ['query_customer_portfolio'],
        'write_operation': False,
        'allows_degradation': False,    # 关键分析，不允许降级
        'timeout_ms': 15000,
        'version': '1.0',
    },

    'query_redemption_quota': {
        'description': '查询产品可赎回额度',
        'required_permission': 'redemption:initiate',
        'params_schema': {
            'type': 'object',
            'required': ['product_id', 'customer_id'],
            'properties': {
                'product_id': {'type': 'string'},
                'customer_id': {'type': 'integer'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 5000,
        'version': '1.0',
    },

    'initiate_redemption': {
        'description': '发起赎回申请（写操作，需人工审核后才实际执行）',
        'required_permission': 'redemption:initiate',
        'params_schema': {
            'type': 'object',
            'required': ['customer_id', 'product_id', 'amount'],
            'properties': {
                'customer_id': {'type': 'integer'},
                'product_id': {'type': 'string'},
                'amount': {'type': 'number', 'minimum': 0.01},
            },
        },
        'depends_on': [],
        'write_operation': True,        # 写操作，全成功才继续
        'allows_degradation': False,
        'timeout_ms': 10000,
        'version': '1.0',
    },

    'query_audit_logs': {
        'description': '查询审计日志（仅 COMPLIANCE 角色可用）',
        'required_permission': 'audit:read',
        'params_schema': {
            'type': 'object',
            'properties': {
                'user_id': {'type': 'integer'},
                'intent_category': {'type': 'string'},
                'start_date': {'type': 'string'},
                'end_date': {'type': 'string'},
            },
        },
        'depends_on': [],
        'write_operation': False,
        'allows_degradation': True,
        'timeout_ms': 8000,
        'version': '1.0',
    },
}
