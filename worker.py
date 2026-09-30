from src.tasks.core.logger import setup_logger

# 消费者 进程 启动时 初始化日志
setup_logger()

# 注册 所有任务
from src.tasks import registry  # noqa: E402, F401

from src.tasks.app import huey  # noqa: E402, F401
