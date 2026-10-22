from django.contrib import admin
from django.urls import path, re_path
from oauth2_provider import views as oauth_views

from apps.core.views import frontend
from apps.mcp import oauth
from apps.mcp.views import mcp

from .api import api

urlpatterns = [
    path("api/", api.urls),
    path("django-admin/", admin.site.urls),
    # The MCP server and its OAuth sign-in. The discovery documents also answer with "/mcp" at
    # the end, the form that some clients ask for.
    path("mcp", mcp),
    path("mcp/", mcp),
    path(".well-known/oauth-protected-resource", oauth.protected_resource),
    path(".well-known/oauth-protected-resource/mcp", oauth.protected_resource),
    path(".well-known/oauth-authorization-server", oauth.authorization_server),
    path(".well-known/oauth-authorization-server/mcp", oauth.authorization_server),
    path("oauth/register", oauth.register),
    path("oauth/authorize/", oauth_views.AuthorizationView.as_view(), name="authorize"),
    path("oauth/token/", oauth_views.TokenView.as_view(), name="token"),
    path("oauth/revoke_token/", oauth_views.RevokeTokenView.as_view(), name="revoke-token"),
    re_path(r"^(?!api/|django-admin/|static/|mcp|oauth/|\.well-known/).*$", frontend),
]
