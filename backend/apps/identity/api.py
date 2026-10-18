from django.contrib.auth import authenticate, login, logout
from django.core.files.base import ContentFile
from django.http import Http404, HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from ninja import Field, File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.security import django_auth
from ninja.utils import check_csrf

from apps.catalog.game_images import JPEG, PNG
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
    # The rights of the original account: it can also make other platform admins.
    is_platform_admin: bool
    can_admin: bool  # True when the user can manage something, so the admin mode is useful.
    can_manage: bool  # True for a championship admin. A steward or custom role is False.
    avatar_url: str | None = None


class Error(Schema):
    detail: str


def _me(user) -> Me:
    return Me(
        id=user.id,
        username=user.username,
        language=user.language,
        timezone=user.timezone,
        is_admin=user.is_staff,
        is_platform_admin=user.is_superuser,
        can_admin=has_any_staff_role(user),
        can_manage=manages_any_championship(user),
        avatar_url=user.avatar_url(),
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


# The browser makes the picture square and small before the upload.
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@router.post("/me/avatar", response=Me, auth=django_auth)
def upload_avatar(request: HttpRequest, file: File[UploadedFile]):
    """Set the picture of the signed-in user. Only a PNG or a JPEG of at most 2 MB."""
    if file.size > MAX_AVATAR_BYTES:
        raise HttpError(400, "image_too_large")
    data = file.read()
    if data.startswith(PNG):
        name = "avatar.png"
    elif data.startswith(JPEG):
        name = "avatar.jpg"
    else:
        raise HttpError(400, "image_not_supported")
    user = request.user
    if user.avatar:
        user.avatar.delete(save=False)
    user.avatar.save(name, ContentFile(data), save=False)
    user.save(update_fields=["avatar"])
    return _me(user)


@router.delete("/me/avatar", response=Me, auth=django_auth)
def remove_avatar(request: HttpRequest):
    user = request.user
    if user.avatar:
        user.avatar.delete(save=False)
        user.save(update_fields=["avatar"])
    return _me(user)


@router.get("/avatars/{user_id}", auth=django_auth)
def avatar(request: HttpRequest, user_id: int):
    """The picture of a user. Every signed-in user can see it, like the names."""
    user = get_object_or_404(User, pk=user_id)
    if not user.avatar:
        raise Http404
    # A picture is at most 2 MB, so the response holds the bytes and no file stays open.
    with user.avatar.open("rb") as handle:
        data = handle.read()
    response = HttpResponse(
        data, content_type="image/png" if data.startswith(PNG) else "image/jpeg"
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    # The address changes with each upload, so the browser can keep the picture.
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    return response
