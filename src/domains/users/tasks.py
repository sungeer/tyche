from datetime import datetime

from huey import crontab

from src.core.queue import huey
from src.core.logger import logger
from src.core.context import run_id_var, new_run_id


@huey.periodic_task(crontab(minute='*/1'))
def health_check():
    """每5分钟执行一次健康检查"""
    run_id_var.set(new_run_id())
    logger.info(f'[Periodic] 健康检查 - {datetime.now()}')
    return {'status': 'healthy'}
