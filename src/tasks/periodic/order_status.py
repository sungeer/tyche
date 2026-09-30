import logging
import time

from huey import crontab

from src.tasks.core.queue import task_queue

logger = logging.getLogger(__name__)


# 每 3 分钟
@task_queue.periodic_task(crontab(minute='*/3'))
def sync_order_status():
    logger.info('begin sync order status')

    time.sleep(3)

    logger.info('end sync order status')
