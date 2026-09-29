import logging
import time

from huey import crontab

from src.tasks.core.queue import task_queue

logger = logging.getLogger(__name__)


# 每天 03:00
@task_queue.periodic_task(crontab(hour='3', minute='0'))
def daily_report():
    logger.info('begin daily report')

    time.sleep(3)

    logger.info('end daily report')
