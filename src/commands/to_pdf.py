import img2pdf
import logging

from src.core import settings
from src.core.base import BaseCommand

logger = logging.getLogger('to_pdf')


def jpg_to_pdf(input_jpg, output_pdf):
    with open(output_pdf, 'wb') as f:
        f.write(img2pdf.convert(input_jpg))


class Command(BaseCommand):
    help = '图片转PDF文件'

    def handle(self, **options):
        logger.info('开始执行图片转为PDF文件')

        try:
            input_jpg = settings.input_dir / 'input.jpg'

            if not input_jpg.exists():
                raise FileNotFoundError(f'文件不存在：{input_jpg}')

            output_pdf = settings.output_dir / 'output.pdf'

            jpg_to_pdf(input_jpg, output_pdf)

            logger.info(f'已保存PDF文件：[{output_pdf}]')
        except (Exception,):
            logger.error('图片转PDF文件失败', exc_info=True)
