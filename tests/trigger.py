# 手动触发一次 send_notification，配合 worker 看日志用
import sys
from pathlib import Path

# 直接跑脚本时 sys.path[0] 是 tests/，把仓库根补上才能 import entrypoint
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entrypoint  # noqa: E402, F401  必须先建 broker，否则消息会发到默认命名空间
from src.background.tasks.notifications import send_notification  # noqa: E402

message = send_notification.send()
print(f'enqueued {message.actor_name} {message.message_id}')
