from huey import crontab

from src.core.queue import huey
from src.core.logger import logger


# 耗时异步任务
@huey.task(retries=3, retry_delay=60)
def process_item_export(item_ids: list[int]):
    logger.info(f"开始导出 {len(item_ids)} 条数据")
    # 耗时逻辑...
    logger.info("导出完成")


# 定时任务 每天凌晨 2 点清理过期数据
@huey.periodic_task(crontab(hour='2', minute='0'))
def cleanup_expired_items():
    logger.info("开始清理过期 items")
    # 清理逻辑...
