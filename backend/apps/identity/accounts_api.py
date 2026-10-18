from datetime import datetime

from django.contrib.auth import login, update_session_auth_hash
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from ninja.security import django_auth
from ninja.utils import check_csrf

from apps.competition.models import ChampionshipMember

from .accounts import (
    AccountError,
    can_make_accounts,
    can_manage_user,
    change_password,
    create_account,
    new_link,
    open_link,
    set_platform_admin,
    use_link,
)
from .models import AccountLink, User

router = Router(tags=["accounts"])

# The token goes after "#" in the link. The browser never sends that part to the server, so the
# token stays out of the access logs. The page then sends the token in a POST body.
INVITE_PATH = "/invite#"


class AccountIn(Schema):
    username: str = Field(min_length=1, max_length=150, pattern=r"^[\w.@+-]+$")
    driver_id: int | None = None
    championship_id: int | None = None
    role: ChampionshipMember.Role | None = None
    # The rights of the original account. Only a platform admin can give them.
    platform_admin: bool = False


class PlatformAdminIn(Schema):
    on: bool


class AccountOut(Schema):
    id: int
    username: str
    is_platform_admin: bool
    driver_name: str | None
    championships: list[str]
    has_password: bool
    open_link: bool
    last_login: datetime | None


class LinkOut(Schema):
    account: AccountOut
    link_path: str  # Add it to the address of the app, for example https://paddock.example.com
    expires_at: datetime


class TokenIn(Schema):
    token: str = Field(min_length=10, max_length=100)


class LinkInfo(Schema):
    username: str
    purpose: str


class AcceptIn(TokenIn):
    password: str = Field(max_length=128)
    password_again: str = Field(max_length=128)


class PasswordIn(Schema):
    current: str = Field(max_length=128)
    new: str = Field(max_length=128)
    new_again: str = Field(max_length=128)


class AccountErrorOut(Schema):
    detail: str
    messages: list[str] = []


def _out(user: User) -> AccountOut:
    profile = getattr(user, "driver_profile", None)
    return AccountOut(
        id=user.id,
        username=user.username,
        is_platform_admin=user.is_superuser,
        driver_name=profile.display_name if profile else None,
        championships=sorted(
            f"{m.championship.name} ({m.role})"
            for m in user.championship_roles.select_related("championship")
        ),
        has_password=user.has_usable_password(),
        open_link=user.account_links.filter(used_at__isnull=True).exists(),
        last_login=user.last_login,
    )


def _link_out(user: User, token: str) -> LinkOut:
    link = user.account_links.filter(used_at__isnull=True).latest("created_at")
    return LinkOut(account=_out(user), link_path=INVITE_PATH + token, expires_at=link.expires_at)


@router.get("/accounts", response=list[AccountOut], auth=django_auth)
def list_accounts(request):
    if not can_make_accounts(request.user):
        raise HttpError(403, "forbidden")
    users = User.objects.filter(is_active=True).order_by("username")
    return [_out(u) for u in users if can_manage_user(request.user, u)]


@router.post("/accounts", response={201: LinkOut}, auth=django_auth)
def create(request, payload: AccountIn):
    if not can_make_accounts(request.user):
        raise HttpError(403, "forbidden")
    try:
        user, token = create_account(
            request.user,
            username=payload.username,
            driver_id=payload.driver_id,
            championship_id=payload.championship_id,
            role=payload.role,
            platform_admin=payload.platform_admin,
        )
    except AccountError as error:
        raise HttpError(403 if error.code == "forbidden" else 422, error.code) from error
    return Status(201, _link_out(user, token))


@router.post("/accounts/{user_id}/link", response=LinkOut, auth=django_auth)
def reset_link(request, user_id: int):
    """A new one-time link, for a forgotten password. Older links stop working."""
    user = get_object_or_404(User, pk=user_id, is_active=True)
    if not can_make_accounts(request.user) or not can_manage_user(request.user, user):
        raise HttpError(403, "forbidden")
    purpose = (
        AccountLink.Purpose.RESET if user.has_usable_password() else AccountLink.Purpose.INVITE
    )
    token = new_link(user, purpose, request.user)
    return _link_out(user, token)


@router.put("/accounts/{user_id}/platform-admin", response=AccountOut, auth=django_auth)
def platform_admin(request, user_id: int, payload: PlatformAdminIn):
    """Give or take the rights of a platform admin. Only a platform admin can do it."""
    user = get_object_or_404(User, pk=user_id, is_active=True)
    try:
        set_platform_admin(request.user, user, payload.on)
    except AccountError as error:
        raise HttpError(403 if error.code == "forbidden" else 422, error.code) from error
    return _out(user)


@router.post("/auth/invite/check", response={200: LinkInfo, 422: AccountErrorOut}, auth=None)
def check_link(request: HttpRequest, payload: TokenIn):
    try:
        link = open_link(payload.token)
    except AccountError as error:
        return Status(422, AccountErrorOut(detail=error.code))
    return LinkInfo(username=link.user.username, purpose=link.purpose)


@router.post(
    "/auth/invite/accept",
    response={200: dict, 403: AccountErrorOut, 422: AccountErrorOut},
    auth=None,
)
def accept_link(request: HttpRequest, payload: AcceptIn):
    if check_csrf(request) is not None:
        return Status(403, AccountErrorOut(detail="csrf"))
    try:
        user = use_link(payload.token, payload.password, payload.password_again)
    except AccountError as error:
        return Status(422, AccountErrorOut(detail=error.code, messages=error.messages))
    login(request, user)
    return {"username": user.username}


@router.post("/auth/password", response={204: None, 422: AccountErrorOut}, auth=django_auth)
def set_password(request: HttpRequest, payload: PasswordIn):
    try:
        change_password(request.user, payload.current, payload.new, payload.new_again)
    except AccountError as error:
        return Status(422, AccountErrorOut(detail=error.code, messages=error.messages))
    # Keep the session after the change. Django signs sessions with the password hash.
    update_session_auth_hash(request, request.user)
    return Status(204, None)
