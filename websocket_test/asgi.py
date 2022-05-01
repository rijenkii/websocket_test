"""
ASGI config for websocket_test project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter, ChannelNameRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

import chat.routing
import chat.consumers

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websocket_test.settings')

application = ProtocolTypeRouter({
    'html': get_asgi_application(),
    'websocket': URLRouter(chat.routing.websocket_urlpatterns),
})
