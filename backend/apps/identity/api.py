from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.middleware.csrf import get_token
from ninja import Router, Schema, Status
from ninja.security import django_auth
from ninja.utils import check_csrf

from apps.competition.permissions import manages_any_championship

router = Router(tags=["auth"])


class Credentials(Schema):
    username: str
    password: str


class Me(Schema):
    id: int
    username: str
    language: str
    is_admin: bool
    can_admin: bool  # True when the user can manage something, so the admin mode is useful.


class Error(Schema):
    detail: str


def _me(user) -> Me:
    return Me(
        id=user.id,
        username=user.username,
        language=user.language,
        is_admin=user.is_staff,
        can_admin=manages_any_championship(user),
    )


@router.get("/csrf", response={204: None}, auth=None)
def csrf(request: HttpRequest):
    """Set the CSRF cookie. The frontend calls this before the login."""
    get_token(request)
    return Status(204, None)


@router.post("/login", response={200: Me, 401: Error, 403: Error}, auth=None)
def login_view(request: HttpRequest, credentials: Credentials):
    if check_csrf(request) is not None:
        return Status(403, Error(detail="csrf"))
    user = authenticate(request, username=credentials.username, password=credentials.password)
    if user is None:
        return Status(401, Error(detail="invalid_credentials"))
    login(request, user)
    return Status(200, _me(user))


@router.post("/logout", response={204: None}, auth=django_auth)
def logout_view(request: HttpRequest):
    logout(request)
    return Status(204, None)


@router.get("/me", response=Me, auth=django_auth)
def me(request: HttpRequest):
    return _me(request.user)
