from src.background.core.logger import setup_logger

# 消费者 进程 启动时 初始化日志
setup_logger()

# 设置 全局 broker，必须先于 任务 导入
from src.background import app  # noqa: E402, F401

# 注册 所有任务
from src.background import registry  # noqa: E402, F401
