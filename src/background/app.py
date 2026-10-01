from huey import RedisHuey

from src import settings

huey = RedisHuey(
    name='tyche',
    results=False,  # 不保存任务结果
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
)
