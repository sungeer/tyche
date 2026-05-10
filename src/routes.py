from starlette.routing import Route

from src.domains.health import views as health_views
from src.domains.auth import views as auth_views

routes = [
    Route('/healthz.startup', health_views.startup_probe, methods=['GET']),  # 应用启动期间
    Route('/healthz.liveness', health_views.liveness, methods=['GET']),  # 运行期间
    Route('/healthz.readiness', health_views.readiness, methods=['GET']),  # 数据库连接等依赖服务

    Route('/auth.token', auth_views.auth_token, methods=['POST']),

    # Route('/agent.chat', agent_views.chat, methods=['POST']),  # 多轮对话 SSE 流式
    # Route('/agent.task.status', agent_views.task_status, methods=['POST']),  # 查询任务状态
    # Route('/agent.review.list', agent_views.review_list, methods=['POST']),  # 查看待审核任务 审核人用
    # Route('/agent.review.approve', agent_views.review_approve, methods=['POST']),  # 审核通过
    # Route('/agent.review.reject', agent_views.review_reject, methods=['POST']),  # 审核驳回
    # Route('/agent.session.clear', agent_views.session_clear, methods=['POST']),  # 清除会话上下文
    # Route('/agent.metrics', agent_views.metrics, methods=['POST']),  # 系统指标 仅 ADMIN
]
