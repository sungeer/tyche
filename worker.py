from src.tasks.core.logger import setup_logger

# 消费者 进程 启动时 初始化日志
setup_logger()

# 注册 所有任务
from src.tasks.background import send_notification
from src.tasks.periodic import (
    daily_report,
    sync_order_status
)

from src.tasks.core.queue import huey
