from starlette.routing import Route

from src.domains.auth import views as auth_views

routes = [
    Route('/auth.token', auth_views.auth_token, methods=['POST']),
]
