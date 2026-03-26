import sys

from loguru import logger


def setup_logger():
    logger.remove()
    logger.add(
        sink=sys.stdout,  # 输出到标准输出流
        format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {message}',  # 日志格式
        level='INFO',
        diagnose=False,  # 关闭变量值
        backtrace=False,  # 关闭完整堆栈跟踪
        colorize=False,
        enqueue=True,  # 启用异步日志处理
        filter=lambda record: record['level'].no < 30,  # 低于 WARNING(30)
    )
    # WARNING 及以上
    logger.add(
        sink=sys.stderr,  # 输出到标准错误流
        format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {message}',  # 日志格式
        level='WARNING',
        diagnose=False,  # 关闭变量值
        backtrace=False,  # 关闭完整堆栈跟踪
        colorize=False,
        enqueue=True,  # 启用异步日志处理
    )
