"""
风险评估相关 Skill 实现
run_stress_test 依赖 query_customer_portfolio 的输出作为入参。
"""
import httpx
from loguru import logger

from src.core.config import settings


async def run_stress_test(params, conn):
    """
    对客户持仓执行压力测试。
    调用行内风控引擎 HTTP 接口（httpx 异步）。
    params 中的 portfolio_snapshot 由 query_customer_portfolio 的结果注入。
    conn 参数不使用，保留以统一 Skill 函数签名。
    """
    payload = {
        'customer_id': params['customer_id'],
        'portfolio': params['portfolio_snapshot'],
        'scenario': params.get('scenario', 'rate_up_100bp'),
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f'{settings.risk_engine_url}/v1/stress-test',
                json=payload,
                headers={'X-Api-Key': settings.risk_engine_api_key},
                timeout=14,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.RequestError as e:
        logger.error(f'[风控引擎] 压力测试调用失败：{e}')
        raise
