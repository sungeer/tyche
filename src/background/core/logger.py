import logging


def setup_logger():
    logging.addLevelName(logging.DEBUG, 'DBG')
    logging.addLevelName(logging.INFO, 'INF')
    logging.addLevelName(logging.WARNING, 'WRN')
    logging.addLevelName(logging.ERROR, 'ERR')
    logging.addLevelName(logging.CRITICAL, 'CRT')

    fmt = '%(asctime)s | %(levelname)s | %(message)s (%(name)s:%(lineno)d)'

    formatter = logging.Formatter(fmt=fmt)

    root_logger = logging.getLogger()

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
