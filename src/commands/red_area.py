import logging

from src.core.base import BaseCommand

logger = logging.getLogger('red_area')


class Command(BaseCommand):
    help = '向某人打招呼'

    def handle(self, **options):
        msg = 'Hello, World!'
        logger.info(msg.upper())
