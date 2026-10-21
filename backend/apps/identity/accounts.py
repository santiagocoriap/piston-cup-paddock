"""Accounts that an admin makes, with one-time links to set the password."""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import change, record
from apps.competition.models import Championship, ChampionshipMember
from apps.competition.permissions import can_manage, is_league_admin

from .models import AccountLink, DriverProfile, User

LINK_LIFETIME = timedelta(days=7)


class AccountError(ValueError):
    def __init__(self, code: str, messages: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.messages = messages or []


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_link(user: User, purpose: str, created_by) -> str:
    """Make a one-time link and give back the token. Older open links of the user stop working."""
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    with transaction.atomic():
        AccountLink.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        AccountLink.objects.create(
            user=user,
            token_hash=_hash(token),
            purpose=purpose,
            expires_at=now + LINK_LIFETIME,
            created_by=created_by,
        )
        record(
            created_by,
            "account.link_created",
            "account",
            user.id,
            params={"username": user.username, "purpose": purpose},
        )
    return token


def can_make_accounts(admin) -> bool:
    return (
        is_league_admin(admin)
        or ChampionshipMember.objects.filter(
            user=admin, role=ChampionshipMember.Role.ADMIN
        ).exists()
    )


def create_account(
    admin,
    *,
    username: str,
    driver_id: int | None,
    championship_id: int | None,
    role: str | None,
    platform_admin: bool = False,
    new_driver: bool = False,
    steam_guid: str | None = None,
) -> tuple[User, str]:
    """An account with a one-time link. new_driver: without driver_id, a new driver profile
    with the user name (and the Steam ID, when given) goes with the account."""
    username = username.strip()
    if not username:
        raise AccountError("username_required")
    if platform_admin and not admin.is_superuser:
        raise AccountError("forbidden")
    championship = None
    if championship_id is not None:
        championship = Championship.objects.filter(pk=championship_id).first()
        if championship is None or not can_manage(admin, championship):
            raise AccountError("forbidden")
    elif not is_league_admin(admin) and not platform_admin:
        # A championship admin adds people only to a championship that the admin manages.
        raise AccountError("championship_required")
    if User.objects.filter(username__iexact=username).exists():
        raise AccountError("username_exists")
    steam_guid = (steam_guid or "").strip() or None
    if steam_guid and DriverProfile.objects.filter(steam_guid=steam_guid).exists():
        raise AccountError("steam_guid_exists")
    profile = None
    if driver_id is not None:
        profile = DriverProfile.objects.filter(pk=driver_id).first()
        if profile is None:
            raise AccountError("driver_not_found")
        if profile.user_id is not None:
            raise AccountError("account_has_profile")
        # A championship admin links only a driver who races in that championship.
        if (
            not is_league_admin(admin)
            and not profile.entries.filter(season__championship=championship).exists()
        ):
            raise AccountError("forbidden")

    with transaction.atomic():
        user = User(username=username, is_staff=platform_admin, is_superuser=platform_admin)
        user.set_unusable_password()
        user.save()
        changes = [change("username", None, username)]
        if platform_admin:
            changes.append(change("platform_admin", False, True))
        if profile is None and new_driver:
            profile = DriverProfile.objects.create(
                display_name=username, user=user, steam_guid=steam_guid
            )
            changes.append(change("driver", None, profile.display_name))
        elif profile:
            profile.user = user
            profile.save(update_fields=["user"])
            changes.append(change("driver", None, profile.display_name))
        if championship:
            ChampionshipMember.objects.create(
                championship=championship, user=user, role=role or ChampionshipMember.Role.DRIVER
            )
            changes.append(change("role", None, f"{championship.name}: {role or 'driver'}"))
        record(
            admin,
            "account.created",
            "account",
            user.id,
            championship=championship,
            params={"username": username},
            changes=changes,
        )
        token = new_link(user, AccountLink.Purpose.INVITE, admin)
    return user, token


def set_platform_admin(admin, user: User, on: bool) -> User:
    """Give or take the rights of the original account: every league, championship, and
    account. Only a platform admin does this. The app always keeps one platform admin, and an
    admin cannot take the own rights, so nobody locks the league out by mistake."""
    if not admin.is_superuser:
        raise AccountError("forbidden")
    if not on:
        if user.pk == admin.pk:
            raise AccountError("own_platform_admin")
        others = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk)
        if not others.exists():
            raise AccountError("last_admin")
    if user.is_superuser == on and user.is_staff == on:
        return user
    with transaction.atomic():
        before = user.is_superuser
        user.is_staff = on
        user.is_superuser = on
        user.save(update_fields=["is_staff", "is_superuser"])
        record(
            admin,
            "account.platform_admin" if on else "account.platform_admin_removed",
            "account",
            user.id,
            params={"username": user.username},
            changes=[change("platform_admin", before, on)],
        )
    return user


def can_manage_user(admin, user: User) -> bool:
    """Who can see an account and make a new link for it.

    A league admin manages every account, but only a superuser manages a superuser. A
    championship admin manages only plain drivers whose roles are all in championships that
    the admin manages. Never an admin, and never the own account, so a link can never give
    more rights to the person who makes it.
    """
    if user.is_superuser and not admin.is_superuser:
        return False
    if is_league_admin(admin):
        return True
    if user.pk == admin.pk or user.is_staff:
        return False
    roles = ChampionshipMember.objects.filter(user=user)
    if roles.exclude(role=ChampionshipMember.Role.DRIVER).exists():
        return False
    managed = set(
        ChampionshipMember.objects.filter(
            user=admin, role=ChampionshipMember.Role.ADMIN
        ).values_list("championship_id", flat=True)
    )
    championships = set(roles.values_list("championship_id", flat=True))
    return bool(championships) and championships <= managed


def open_link(token: str) -> AccountLink:
    link = AccountLink.objects.select_related("user").filter(token_hash=_hash(token)).first()
    if link is None or link.used_at is not None or link.expires_at < timezone.now():
        raise AccountError("link_not_valid")
    return link


def _validate(password: str, user: User) -> None:
    try:
        password_validation.validate_password(password, user)
    except ValidationError as error:
        raise AccountError("weak_password", list(error.messages)) from error


def use_link(token: str, password: str, password_again: str) -> User:
    link = open_link(token)
    if password != password_again:
        raise AccountError("passwords_differ")
    _validate(password, link.user)
    with transaction.atomic():
        link.user.set_password(password)
        link.user.save(update_fields=["password"])
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
        record(
            link.user,
            "account.password_set",
            "account",
            link.user.id,
            params={"username": link.user.username, "purpose": link.purpose},
        )
    return link.user


def change_password(user: User, current: str, new: str, new_again: str) -> None:
    if not user.check_password(current):
        raise AccountError("wrong_current_password")
    if new != new_again:
        raise AccountError("passwords_differ")
    _validate(new, user)
    with transaction.atomic():
        user.set_password(new)
        user.save(update_fields=["password"])
        record(
            user, "account.password_changed", "account", user.id, params={"username": user.username}
        )
