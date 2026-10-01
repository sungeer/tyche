import logging
import sys

from src.background.core.logger import setup_logger


def _reset_root_logger():
    # setup_logger 改的是全局 root logger，测完要还原
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    return root_logger


def test_setup_logger_attaches_single_stdout_handler():
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    _reset_root_logger()
    try:
        setup_logger()

        assert len(root_logger.handlers) == 1
        handler = root_logger.handlers[0]
        assert handler.stream is sys.stdout
    finally:
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)


def test_record_reaches_stdout(capsys):
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    _reset_root_logger()
    try:
        setup_logger()
        logging.getLogger('tests.sample').info('hello tyche')
    finally:
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)

    assert 'INF | hello tyche (tests.sample' in capsys.readouterr().out
