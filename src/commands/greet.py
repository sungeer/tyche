import logging

from src.core.base import BaseCommand

logger = logging.getLogger('red_area')


class Command(BaseCommand):
    help = '向某人打招呼'

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='名字')
        parser.add_argument('--upper', action='store_true', help='大写输出')

    def handle(self, name, upper=False, **options):
        msg = f'Hello, {name}!'
        print(msg.upper() if upper else msg)
