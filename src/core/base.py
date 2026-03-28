import argparse


class BaseCommand:
    help = 'No description provided.'

    def create_parser(self, prog, subcommand):
        parser = argparse.ArgumentParser(
            prog=f'{prog} {subcommand}',
            description=self.help,
        )
        self.add_arguments(parser)
        return parser

    def add_arguments(self, parser):
        """子类可覆写，用于添加参数"""
        pass

    def handle(self, **options):
        """子类必须实现此方法"""
        raise NotImplementedError('必须实现 handle() 方法')

    def execute(self, **options):
        self.handle(**options)
