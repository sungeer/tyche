from datetime import datetime

from huey import crontab

from src.core.worker import huey
from src.core.logger import logger


@huey.periodic_task(crontab(minute='*/1'))
def health_check():
    """每5分钟执行一次健康检查"""
    logger.info(f"[Periodic] 健康检查 - {datetime.now()}")
    return {'status': 'healthy'}
