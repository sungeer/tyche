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
        enqueue=True  # 启用异步日志处理
    )
