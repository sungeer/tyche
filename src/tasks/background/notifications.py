import logging
import time

from src.tasks.app import huey

logger = logging.getLogger(__name__)


@huey.task(retries=3, retry_delay=30)
def send_notification():
    logger.info('begin send notification')

    time.sleep(3)

    logger.info('end send notification')
