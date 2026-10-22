"""The tools of the MCP server. They run inside the app, as the signed-in person: every call goes
through the same API view, permission check, and audit log as a click in the app."""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlencode

from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import Resolver404, resolve

# Operations that the tools do not offer: the sign-in itself, the collector and the game script
# (they use their own keys), and file uploads (a tool cannot send a file). Also the accounts and
# the access rights: accounts, invite links, platform admins, deleted accounts, and the Claude
# connections. Text from other people comes back in the tool answers, and it could try to steer
# Claude: a change of who has access stays a click of the person in the app.
# Sign-in, accounts, and access rights stay in the app UI: text in the app data must not be
# able to make Claude give access to a person. Collector and script keys are access rights
# too, and so is the link between a driver and an account (a merge moves that link).
HIDDEN = re.compile(
    r"^/api/(auth/|collector/|script/|avatars/|accounts|me/connections|objects/user/"
    r"|championships/[^/]+/(members|roles|collectors|script)|roles/|collectors/"
    r"|drivers/[^/]+/(link|merge))"
)
MAX_TEXT = 60_000


@dataclass
class Operation:
    method: str
    path: str
    summary: str
    description: str
    tags: list[str]
    parameters: list[dict] = field(default_factory=list)
    body: dict | None = None

    @property
    def id(self) -> str:
        return f"{self.method} {self.path}"

    def words(self) -> str:
        return " ".join(
            [self.method, self.path, self.summary, self.description, *self.tags]
        ).lower()


def _resolve(schema: dict, components: dict, depth: int = 0) -> dict:
    """The schema with each $ref replaced, 4 levels deep at most, so the tool shows the fields."""
    if depth > 4:
        return {"type": "object"}
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _resolve(components.get(name, {}), components, depth + 1)
    out: dict = {}
    for key, value in schema.items():
        if key in ("title",):
            continue
        if isinstance(value, dict):
            out[key] = _resolve(value, components, depth + 1)
        elif isinstance(value, list):
            out[key] = [
                _resolve(v, components, depth + 1) if isinstance(v, dict) else v for v in value
            ]
        else:
            out[key] = value
    return out


@lru_cache(maxsize=1)
def catalog() -> list[Operation]:
    """The operations of the app API, from its OpenAPI description."""
    from config.api import api

    schema = api.get_openapi_schema()
    components = schema.get("components", {}).get("schemas", {})
    found = []
    for path, methods in schema.get("paths", {}).items():
        if HIDDEN.match(path):
            continue
        for method, spec in methods.items():
            content = (spec.get("requestBody") or {}).get("content", {})
            if "multipart/form-data" in content:
                continue
            body = content.get("application/json", {}).get("schema")
            found.append(
                Operation(
                    method=method.upper(),
                    path=path,
                    summary=spec.get("summary", ""),
                    description=(spec.get("description") or "").strip()[:400],
                    tags=spec.get("tags", []),
                    parameters=[
                        {
                            "name": p["name"],
                            "in": p["in"],
                            "required": p.get("required", False),
                            "schema": _resolve(p.get("schema", {}), components),
                        }
                        for p in spec.get("parameters", [])
                    ],
                    body=_resolve(body, components) if body else None,
                )
            )
    return found


def search(query: str, limit: int = 8) -> list[dict]:
    """The operations that match the words of the query best."""
    words = [w for w in re.split(r"[^\w/]+", query.lower()) if w]
    scored = []
    for op in catalog():
        text = op.words()
        score = sum(text.count(w) for w in words)
        if score:
            scored.append((score, op))
    scored.sort(key=lambda item: (-item[0], item[1].path))
    return [
        {
            "method": op.method,
            "path": op.path,
            "summary": op.summary,
            "description": op.description,
            "parameters": op.parameters,
            "body": op.body,
        }
        for _, op in scored[:limit]
    ]


def _pattern(path: str) -> str:
    """A regular expression for an API path: "{season_id}" matches one part of the path."""
    return "^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(path)) + "$"


def _match(method: str, path: str) -> Operation | None:
    for op in catalog():
        if op.method == method and re.match(_pattern(op.path), path):
            return op
    return None


class ToolError(ValueError):
    pass


def call(user, method: str, path: str, query: dict | None = None, body=None) -> dict:
    """Run one API operation as the user. Gives the status and the answer of the app."""
    method = method.upper()
    if not path.startswith("/api/"):
        path = "/api/" + path.lstrip("/")
    if HIDDEN.match(path):
        raise ToolError("This operation is not available to the tools.")
    if _match(method, path) is None:
        raise ToolError(
            f"No operation {method} {path}. Use search_operations to find the right path."
        )
    url = path + (f"?{urlencode(query, doseq=True)}" if query else "")
    factory = RequestFactory()
    if body is None:
        request = factory.generic(method, url)
    else:
        request = factory.generic(
            method, url, data=json.dumps(body), content_type="application/json"
        )
    request.user = user
    # The person signed in with OAuth, not with a cookie: there is no CSRF risk here.
    request._dont_enforce_csrf_checks = True
    try:
        match = resolve(path)
    except Resolver404 as error:
        raise ToolError(f"No operation {method} {path}.") from error
    response: HttpResponse = match.func(request, *match.args, **match.kwargs)
    return {"status": response.status_code, "body": _body(response)}


def _body(response: HttpResponse):
    kind = response.get("Content-Type", "")
    if getattr(response, "streaming", False):
        return f"(a file: {kind})"
    raw = response.content
    if "json" in kind:
        try:
            return json.loads(raw or b"null")
        except ValueError:
            pass
    if kind.startswith(("text/", "application/csv")):
        text = raw.decode("utf-8", "replace")
        return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n(cut)"
    return f"(a file: {kind}, {len(raw)} bytes)"


def overview(user) -> dict:
    """Who the person is, and the leagues, championships, and seasons that they can see."""
    from apps.competition.models import Season
    from apps.competition.permissions import can_manage, visible_championships

    championships = visible_championships(user).select_related("league")
    seasons = Season.objects.filter(championship__in=championships).order_by("-created_at")
    return {
        "user": {
            "username": user.username,
            "platform_admin": user.is_superuser,
            "league_admin": user.is_staff,
        },
        "championships": [
            {
                "id": c.id,
                "name": c.name,
                "league": c.league.name,
                "can_manage": can_manage(user, c),
                "seasons": [
                    {"id": s.id, "name": s.name} for s in seasons if s.championship_id == c.id
                ],
            }
            for c in championships
        ],
    }
