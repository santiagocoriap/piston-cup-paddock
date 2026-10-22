"""The MCP server: OAuth sign-in for Claude, and the tools that run as the signed-in person."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client

from apps.competition.models import League

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "a" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


def register(client: Client) -> str:
    answer = client.post(
        "/oauth/register",
        json.dumps({"redirect_uris": [REDIRECT], "client_name": "Claude"}),
        content_type="application/json",
    )
    assert answer.status_code == 201, answer.content
    return answer.json()["client_id"]


def token_for(user) -> str:
    """The full flow of claude.ai: register, sign in, allow, and swap the code for a token."""
    client = Client()
    client_id = register(client)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "scope": "mcp",
        "state": "xyz",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    client.force_login(user)
    page = client.get("/oauth/authorize/", params)
    assert page.status_code == 200
    assert "Permitir" in page.content.decode()
    allowed = client.post("/oauth/authorize/", {**params, "allow": "Authorize"})
    assert allowed.status_code == 302
    query = parse_qs(urlparse(allowed["Location"]).query)
    assert query["state"] == ["xyz"]
    token = Client().post(
        "/oauth/token/",
        {
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": VERIFIER,
        },
    )
    assert token.status_code == 200, token.content
    return token.json()["access_token"]


def rpc(token: str, method: str, params: dict | None = None, id_=1):
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        message["id"] = id_
    return Client().post(
        "/mcp",
        json.dumps(message),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def tool(token: str, name: str, **arguments) -> dict:
    answer = rpc(token, "tools/call", {"name": name, "arguments": arguments})
    assert answer.status_code == 200
    result = answer.json()["result"]
    return {"error": result["isError"], "data": json.loads(result["content"][0]["text"])}


def test_the_discovery_documents(db):
    client = Client()
    resource = client.get("/.well-known/oauth-protected-resource").json()
    assert resource["resource"].endswith("/mcp")
    server = client.get(
        resource["authorization_servers"][0] + "/.well-known/oauth-authorization-server"
    )
    data = server.json()
    assert data["registration_endpoint"].endswith("/oauth/register")
    assert data["code_challenge_methods_supported"] == ["S256"]
    assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 200


def test_mcp_without_a_token_says_where_to_sign_in(db):
    answer = Client().post("/mcp", "{}", content_type="application/json")
    assert answer.status_code == 401
    assert "resource_metadata=" in answer["WWW-Authenticate"]
    assert Client().get("/mcp").status_code in (401, 405)


def test_a_registration_needs_an_https_address(db):
    answer = Client().post(
        "/oauth/register",
        json.dumps({"redirect_uris": ["http://evil.example.com/cb"]}),
        content_type="application/json",
    )
    assert answer.status_code == 400


def test_the_sign_in_goes_to_the_app_login(db):
    client = Client()
    client_id = register(client)
    answer = client.get(
        "/oauth/authorize/",
        {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT},
    )
    assert answer.status_code == 302
    assert answer["Location"].startswith("/sign-in?next=")


@pytest.fixture
def admin_token(make_user):
    return token_for(make_user("owner", is_staff=True, is_superuser=True))


def test_initialize_and_the_tool_list(admin_token):
    init = rpc(admin_token, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert "tools" in init["capabilities"]
    assert rpc(admin_token, "notifications/initialized", id_=None).status_code == 202
    names = {t["name"] for t in rpc(admin_token, "tools/list").json()["result"]["tools"]}
    assert names == {"overview", "search_operations", "api_read", "api_write"}


def test_the_tools_read_and_change_the_app(admin_token):
    found = tool(admin_token, "search_operations", query="leagues")["data"]
    assert any(op["path"] == "/api/leagues" and op["method"] == "POST" for op in found)
    made = tool(
        admin_token, "api_write", method="POST", path="/api/leagues", body={"name": "MCP Cup"}
    )
    assert not made["error"], made
    assert League.objects.filter(name="MCP Cup").exists()
    listed = tool(admin_token, "api_read", path="/api/leagues")
    assert any(league["name"] == "MCP Cup" for league in listed["data"]["body"])
    overview = tool(admin_token, "overview")["data"]
    assert overview["user"]["platform_admin"] is True


def test_a_driver_keeps_the_rights_of_a_driver(make_user):
    token = token_for(make_user("racer"))
    answer = tool(token, "api_write", method="POST", path="/api/leagues", body={"name": "Nope"})
    assert answer["error"] and answer["data"]["status"] == 403
    assert not League.objects.filter(name="Nope").exists()


def test_an_unknown_or_hidden_path_is_refused(admin_token):
    assert tool(admin_token, "api_read", path="/api/nothing/here")["error"]
    assert tool(admin_token, "api_write", method="POST", path="/api/auth/logout")["error"]
    assert tool(admin_token, "api_write", method="GET", path="/api/leagues")["error"]


def test_the_person_sees_and_removes_a_connection(api, make_user):
    user = make_user("owner2", is_staff=True)
    token = token_for(user)
    rows = api(user).get("/me/connections").json()
    assert [r["name"] for r in rows] == ["Claude"] and rows[0]["active"]
    assert api(user).delete(f"/me/connections/{rows[0]['application_id']}").status_code == 204
    assert rpc(token, "tools/list").status_code == 401
