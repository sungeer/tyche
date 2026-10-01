import logging
import sys


def setup_logger():
    root_logger = logging.getLogger()

    logging.addLevelName(logging.DEBUG, 'DBG')
    logging.addLevelName(logging.INFO, 'INF')
    logging.addLevelName(logging.WARNING, 'WRN')
    logging.addLevelName(logging.ERROR, 'ERR')
    logging.addLevelName(logging.CRITICAL, 'CRT')

    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)s | %(message)s (%(name)s:%(lineno)d)'
    )

    # 消费者进程的 stdout 已被 dramatiq 换成通往主进程的管道，记录统一由主进程落盘
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
