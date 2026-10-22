"""OAuth for the MCP server: the discovery documents and the registration of a client.

claude.ai (and Claude Code, and the phone app) find the sign-in from these documents. The
client registers itself (Dynamic Client Registration, RFC 7591), then the person signs in to
the app and allows the access on the consent page. The authorize and token steps are the views
of django-oauth-toolkit.
"""

import json
from urllib.parse import urlparse

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from oauth2_provider.models import get_application_model

from apps.common.urls import is_local, public_url

SCOPE = "mcp"


def resource_url(request: HttpRequest) -> str:
    return f"{public_url(request)}/mcp"


@require_GET
def protected_resource(request: HttpRequest) -> JsonResponse:
    """RFC 9728: where the MCP server sends a client to sign in."""
    base = public_url(request)
    return JsonResponse(
        {
            "resource": f"{base}/mcp",
            "authorization_servers": [base],
            "scopes_supported": [SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_name": "Piston Cup Paddock",
        }
    )


@require_GET
def authorization_server(request: HttpRequest) -> JsonResponse:
    """RFC 8414: the OAuth endpoints of the app."""
    base = public_url(request)
    return JsonResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize/",
            "token_endpoint": f"{base}/oauth/token/",
            "revocation_endpoint": f"{base}/oauth/revoke_token/",
            "registration_endpoint": f"{base}/oauth/register",
            "scopes_supported": [SCOPE],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )


def _redirect_ok(uri: str) -> bool:
    """HTTPS, or HTTP only for an address on the same computer (a local client)."""
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and is_local(uri)


# The callback hosts of Claude. Claude Code uses an address on the same computer.
TRUSTED_HOSTS = {"claude.ai", "claude.com"}
TRUSTED_NAMES = ("claude", "anthropic")


def _trusted_host(uri: str) -> bool:
    host = urlparse(uri).hostname or ""
    return host in TRUSTED_HOSTS or is_local(uri)


def _claims_trusted_name(name: str) -> bool:
    return any(word in name.lower() for word in TRUSTED_NAMES)


@csrf_exempt
@require_http_methods(["POST"])
def register(request: HttpRequest) -> JsonResponse:
    """RFC 7591: a client registers itself. It gets a public client ID (no secret): the person
    still signs in and allows the access, and PKCE protects the code."""
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)
    uris = data.get("redirect_uris")
    if not isinstance(uris, list) or not uris or not all(isinstance(u, str) for u in uris):
        return JsonResponse(
            {"error": "invalid_redirect_uri", "error_description": "redirect_uris is required"},
            status=400,
        )
    if not all(_redirect_ok(u) for u in uris):
        return JsonResponse(
            {"error": "invalid_redirect_uri", "error_description": "use https"}, status=400
        )
    name = str(data.get("client_name") or "MCP client")[:180]
    if _claims_trusted_name(name) and not all(_trusted_host(u) for u in uris):
        # Anyone can register a client. A name that says Claude, with an address that is not
        # of Claude, could fool the person on the consent page.
        name = f"{name} (no verificado)"
    application = get_application_model().objects.create(
        name=name,
        client_type="public",
        authorization_grant_type="authorization-code",
        redirect_uris=" ".join(uris),
        skip_authorization=False,
        algorithm="",
    )
    return JsonResponse(
        {
            "client_id": application.client_id,
            "client_id_issued_at": int(application.created.timestamp()),
            "client_name": name,
            "redirect_uris": uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
        status=201,
    )
