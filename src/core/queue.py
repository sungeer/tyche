from huey import RedisHuey, MemoryHuey

from src.core.config import settings

# huey = RedisHuey(
#     name=settings.APP_NAME,
#     host=settings.REDIS_HOST,
#     port=settings.REDIS_PORT,
#     db=settings.REDIS_DB,
# )

huey = MemoryHuey('my-app')
