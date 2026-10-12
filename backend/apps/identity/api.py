from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.middleware.csrf import get_token
from ninja import Field, Router, Schema, Status
from ninja.security import django_auth
from ninja.utils import check_csrf

from apps.common.timezones import is_timezone
from apps.competition.permissions import has_any_staff_role, manages_any_championship

from .models import User
from .throttle import clear_failures, client_ip, is_blocked, record_failure

router = Router(tags=["auth"])


class Credentials(Schema):
    username: str
    password: str


class Me(Schema):
    id: int
    username: str
    language: str
    timezone: str
    is_admin: bool
    can_admin: bool  # True when the user can manage something, so the admin mode is useful.
    can_manage: bool  # True for a championship admin. A steward or custom role is False.


class Error(Schema):
    detail: str


def _me(user) -> Me:
    return Me(
        id=user.id,
        username=user.username,
        language=user.language,
        timezone=user.timezone,
        is_admin=user.is_staff,
        can_admin=has_any_staff_role(user),
        can_manage=manages_any_championship(user),
    )


@router.get("/csrf", response={204: None}, auth=None)
def csrf(request: HttpRequest):
    """Set the CSRF cookie. The frontend calls this before the login."""
    get_token(request)
    return Status(204, None)


@router.post("/login", response={200: Me, 401: Error, 403: Error, 429: Error}, auth=None)
def login_view(request: HttpRequest, credentials: Credentials):
    if check_csrf(request) is not None:
        return Status(403, Error(detail="csrf"))
    ip = client_ip(request)
    if is_blocked(credentials.username, ip):
        return Status(429, Error(detail="too_many_attempts"))
    user = authenticate(request, username=credentials.username, password=credentials.password)
    if user is None:
        record_failure(credentials.username, ip)
        return Status(401, Error(detail="invalid_credentials"))
    clear_failures(credentials.username)
    login(request, user)
    return Status(200, _me(user))


@router.post("/logout", response={204: None}, auth=django_auth)
def logout_view(request: HttpRequest):
    logout(request)
    return Status(204, None)


@router.get("/me", response=Me, auth=django_auth)
def me(request: HttpRequest):
    return _me(request.user)


class Settings(Schema):
    language: User.Language | None = None
    timezone: str | None = Field(None, max_length=64)


@router.patch("/me", response={200: Me, 422: Error}, auth=django_auth)
def update_me(request: HttpRequest, payload: Settings):
    """Change the language or the timezone of the signed-in user. An empty timezone means the
    timezone of the browser."""
    user = request.user
    if payload.timezone and not is_timezone(payload.timezone):
        return Status(422, Error(detail="bad_timezone"))
    if payload.language is not None:
        user.language = payload.language
    if payload.timezone is not None:
        user.timezone = payload.timezone
    user.save(update_fields=["language", "timezone"])
    return Status(200, _me(user))
