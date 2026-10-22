import json

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.oauth2_backends import get_oauthlib_core

from apps.common.urls import public_url

from . import server
from .oauth import SCOPE, resource_url


def _unauthorized(request: HttpRequest) -> HttpResponse:
    """RFC 9728: the client learns where to sign in from this header."""
    response = JsonResponse({"error": "invalid_token"}, status=401)
    response["WWW-Authenticate"] = (
        f'Bearer resource_metadata="{public_url(request)}/.well-known/oauth-protected-resource", '
        f'scope="{SCOPE}"'
    )
    return response


@csrf_exempt
def mcp(request: HttpRequest) -> HttpResponse:
    """The MCP endpoint. Only POST: the server sends no stream, so GET has nothing to give."""
    if request.method != "POST":
        response = HttpResponse(status=405)
        response["Allow"] = "POST"
        return response
    valid, oauth_request = get_oauthlib_core().verify_request(request, scopes=[SCOPE])
    if not valid or not oauth_request.user.is_active:
        return _unauthorized(request)
    user = oauth_request.user
    try:
        payload = json.loads(request.body or b"null")
    except ValueError:
        return JsonResponse(server._error(None, -32700, "Parse error"), status=400)
    if isinstance(payload, list):
        answers = [a for a in (server.handle(user, m) for m in payload) if a is not None]
        return JsonResponse(answers, safe=False) if answers else HttpResponse(status=202)
    answer = server.handle(user, payload)
    if answer is None:
        return HttpResponse(status=202)
    response = JsonResponse(answer)
    response["Cache-Control"] = "no-store"
    return response


__all__ = ["mcp", "resource_url"]
