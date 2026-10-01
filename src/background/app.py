import dramatiq
from dramatiq.brokers.redis import RedisBroker

from src import settings

broker = RedisBroker(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    namespace='tyche',
)

dramatiq.set_broker(broker)
