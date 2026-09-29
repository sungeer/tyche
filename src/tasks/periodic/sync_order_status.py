import logging
import time

from huey import crontab

from src.tasks.core.queue import huey

logger = logging.getLogger(__name__)


# 每 5 分钟
@huey.periodic_task(crontab(minute='*/5'))
def sync_order_status():
    logger.info('begin sync order status')

    time.sleep(3)

    logger.info('end sync order status')
