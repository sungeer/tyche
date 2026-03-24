from starlette.routing import Route

from hostess.domains.tasks import views as task_views
from hostess.domains.users import views as user_views

routes = [
    Route('/health.live', health_live, methods=['GET']),  # 存活探针
    Route('/health.ready', health_ready, methods=['GET']),  # 就绪探针
    Route('/health.check', health_check, methods=['POST']),  # 主动检查
    Route('/task.list', task_views.task_list, methods=['POST']),
    Route('/user.get', user_views.user_get, methods=['POST']),
]
