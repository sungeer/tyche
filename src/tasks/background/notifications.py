import logging
import time

from src.tasks.core.queue import task_queue

logger = logging.getLogger(__name__)


@task_queue.task(retries=3, retry_delay=30)
def send_notification():
    logger.info('begin send otification')

    time.sleep(3)

    logger.info('end send notification')
