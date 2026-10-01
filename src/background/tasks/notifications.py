import logging
import time

import dramatiq

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3, min_backoff=30000)
def send_notification():
    logger.info('begin send notification')

    time.sleep(3)

    logger.info('end send notification')
