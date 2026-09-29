from src.core.logger import setup_logger

# 消费者 进程 启动时 初始化日志
setup_logger()

# 注册 所有任务
import src.domains.items.tasks  # noqa
import src.domains.users.tasks  # noqa

from src.core.queue import huey  # noqa
