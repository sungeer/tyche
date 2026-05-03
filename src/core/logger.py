import sys

from loguru import logger

from src.core.context import run_id_var
from src.core.config import settings


def setup_logger():
    logger.remove()

    def inject_run_id(record):
        record['extra']['run_id'] = run_id_var.get('-')

    logger.configure(patcher=inject_run_id)

    logger.add(
        settings.log_path,
        rotation='200MB',
        format='{time:YYYY-MM-DD HH:mm:ss} - {level} - {message}',
        encoding='utf-8',
        enqueue=True,
        diagnose=False,
        backtrace=False,
        colorize=False,
        level='INFO'
    )

    logger.add(
        sink=sys.stdout,  # 标准输出流
        format='{time:YYYY-MM-DD HH:mm:ss} - {level} - [{extra[run_id]}] {message}',  # 日志格式
        level='INFO',
        diagnose=False,  # 关闭变量值
        backtrace=False,  # 关闭完整堆栈跟踪
        colorize=False,
        enqueue=True,  # 启用异步日志处理
    )
