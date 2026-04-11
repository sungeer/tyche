from starlette.routing import Route

from src.domains.auth import views as auth_views
from src.domains.agent import views as agent_views

routes = [
    Route('/auth.token', auth_views.auth_token, methods=['POST']),

    # Agent 多轮对话
    Route('/agent.chat',            agent_views.chat,           methods=['POST']),
    Route('/agent.task.status',     agent_views.task_status,    methods=['POST']),
    Route('/agent.review.list',     agent_views.review_list,    methods=['POST']),
    Route('/agent.review.approve',  agent_views.review_approve, methods=['POST']),
    Route('/agent.review.reject',   agent_views.review_reject,  methods=['POST']),
    Route('/agent.session.clear',   agent_views.session_clear,  methods=['POST']),
    Route('/agent.metrics',         agent_views.metrics,        methods=['POST']),
]
