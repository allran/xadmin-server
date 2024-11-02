"""
ASGI config for server project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.core.handlers.asgi import ASGIRequest
from django.utils.module_loading import import_string

from common.utils import get_logger
from message.routing import urlpatterns as message_urlpatterns
from server.utils import set_current_request

logger = get_logger(__name__)

urlpatterns = message_urlpatterns


@database_sync_to_async
def get_signature_user(scope):
    if scope['type'] == 'websocket':
        scope['method'] = 'GET'

    request = ASGIRequest(scope, None)
    for backend_str in settings.REST_FRAMEWORK.get('DEFAULT_AUTHENTICATION_CLASSES'):
        try:
            backend = import_string(backend_str)
            user, _ = backend().authenticate(request)
            if user:
                request.user = user
                set_current_request(request)
                logger.info(f"web socket auth success")
                return user
        except Exception as e:
            logger.warning(f"web socket auth failed by {backend_str}. Exception: {e}")
    logger.error(f"web socket auth failed.")
    return None


class WsSignatureAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        user = await get_signature_user(scope)
        if user:
            scope['user'] = user
        return await self.app(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AllowedHostsOriginValidator(
            WsSignatureAuthMiddleware(
                AuthMiddlewareStack(URLRouter(urlpatterns))
            )
        ),
    }
)
