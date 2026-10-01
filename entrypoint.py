from src.background.core.logger import setup_logger

setup_logger()

from src.background import broker  # noqa: F401
from src.background import tasks  # noqa: F401
