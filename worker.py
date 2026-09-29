from src.tasks.core.logger import setup_logger

# 消费者 进程 启动时 初始化日志
setup_logger()

# 注册 所有任务 触发装饰器挂载到 task_queue
from src.tasks import registry  # noqa

from src.tasks.core.queue import task_queue  # noqa
