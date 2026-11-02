from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.audit.services import change, record
from apps.common.api import conflict_on_duplicate, require
from apps.competition.permissions import is_league_admin, manages_any_championship

from .merge import MergeError, merge
from .models import DriverProfile, DriverSteamId, User, guid_in_use

router = Router(tags=["drivers"])


class DriverIn(Schema):
    display_name: str = Field(min_length=1, max_length=100)
    steam_guid: str | None = Field(None, pattern=r"^\d{17}$")


class DriverOut(Schema):
    id: int
    display_name: str
    steam_guid: str | None
    extra_guids: list[str] = []  # More Steam accounts of the same driver.
    user_id: int | None
    username: str | None
    career_points: int = 0

    @staticmethod
    def resolve_username(profile: DriverProfile) -> str | None:
        return profile.user.username if profile.user else None

    @staticmethod
    def resolve_extra_guids(profile: DriverProfile) -> list[str]:
        return [row.guid for row in profile.extra_guids.all()]


class LinkIn(Schema):
    user_id: int | None


class UserOut(Schema):
    id: int
    username: str


@router.get("/drivers", response=list[DriverOut])
def list_drivers(request):
    """Career points are the official points of all seasons."""
    from apps.results.services import career_points

    profiles = list(DriverProfile.objects.select_related("user").prefetch_related("extra_guids"))
    totals = career_points([p.id for p in profiles])
    for profile in profiles:
        profile.career_points = totals[profile.id]
    return profiles


@router.post("/drivers", response={201: DriverOut})
def create_driver(request, payload: DriverIn):
    require(manages_any_championship(request.user))
    if payload.steam_guid and guid_in_use(payload.steam_guid):
        raise HttpError(409, "steam_guid_exists")
    with conflict_on_duplicate("steam_guid_exists"):
        profile = DriverProfile.objects.create(**payload.dict())
        record(
            request.user,
            "driver.created",
            "driver",
            profile.id,
            params={"driver": profile.display_name},
            changes=[change("steam_guid", None, profile.steam_guid)],
        )
    return Status(201, profile)


class DriverEditIn(Schema):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    # 17 digits, or "" to remove the Steam ID.
    steam_guid: str | None = Field(None, pattern=r"^(\d{17})?$")


@router.patch("/drivers/{driver_id}", response=DriverOut)
def edit_driver(request, driver_id: int, payload: DriverEditIn):
    """An admin changes the name or the Steam ID of a driver. The server entry list and the
    result import use the new Steam ID from the next push. The Steam ID is the identity of the
    driver on the server: only a league admin changes or removes one, like a link to an
    account. A championship admin can give a Steam ID to a driver who has none."""
    require(manages_any_championship(request.user))
    profile = get_object_or_404(DriverProfile.objects.select_related("user"), pk=driver_id)
    changes = []
    if payload.display_name is not None and payload.display_name.strip() != profile.display_name:
        name = payload.display_name.strip()
        changes.append(change("display_name", profile.display_name, name))
        profile.display_name = name
    if payload.steam_guid is not None:
        guid = payload.steam_guid or None
        if guid != profile.steam_guid:
            require(profile.steam_guid is None or is_league_admin(request.user))
            if guid and guid_in_use(guid, exclude=profile):
                raise HttpError(409, "steam_guid_exists")
            # A main Steam ID that was an extra one of this driver stops being extra.
            profile.extra_guids.filter(guid=guid).delete()
            changes.append(change("steam_guid", profile.steam_guid, guid))
            profile.steam_guid = guid
    with conflict_on_duplicate("steam_guid_exists"):
        profile.save(update_fields=["display_name", "steam_guid"])
        if changes:
            record(
                request.user,
                "driver.changed",
                "driver",
                profile.id,
                params={"driver": profile.display_name},
                changes=changes,
            )
    return profile


class ExtraGuidIn(Schema):
    guid: str = Field(pattern=r"^\d{17}$")


@router.post("/drivers/{driver_id}/steam-ids", response=DriverOut)
def add_steam_id(request, driver_id: int, payload: ExtraGuidIn):
    """Add a Steam account to a driver who races with more than one. The Steam ID must be free:
    no driver has it."""
    require(manages_any_championship(request.user))
    profile = get_object_or_404(DriverProfile.objects.select_related("user"), pk=driver_id)
    if payload.guid in profile.guids():
        return profile
    # A second Steam ID is like a change of the Steam ID: only a league admin.
    require(profile.steam_guid is None or is_league_admin(request.user))
    if guid_in_use(payload.guid):
        raise HttpError(409, "steam_guid_exists")
    with conflict_on_duplicate("steam_guid_exists"):
        if profile.steam_guid:
            DriverSteamId.objects.create(driver=profile, guid=payload.guid)
        else:
            profile.steam_guid = payload.guid
            profile.save(update_fields=["steam_guid"])
        record(
            request.user,
            "driver.steam_id_added",
            "driver",
            profile.id,
            params={"driver": profile.display_name},
            changes=[change("steam_guid", None, payload.guid)],
        )
    return profile


@router.delete("/drivers/{driver_id}/steam-ids/{guid}", response=DriverOut)
def remove_steam_id(request, driver_id: int, guid: str):
    """Remove an extra Steam ID. Only a league admin, like a change of the main Steam ID."""
    require(is_league_admin(request.user))
    profile = get_object_or_404(DriverProfile.objects.select_related("user"), pk=driver_id)
    removed, _ = profile.extra_guids.filter(guid=guid).delete()
    if removed:
        record(
            request.user,
            "driver.steam_id_removed",
            "driver",
            profile.id,
            params={"driver": profile.display_name},
            changes=[change("steam_guid", guid, None)],
        )
    return profile


@router.post("/drivers/{driver_id}/link", response=DriverOut)
def link_driver(request, driver_id: int, payload: LinkIn):
    """Link a driver profile to an account, or remove the link with user_id null."""
    require(is_league_admin(request.user))
    profile = get_object_or_404(DriverProfile, pk=driver_id)
    old_username = profile.user.username if profile.user else None
    profile.user = get_object_or_404(User, pk=payload.user_id) if payload.user_id else None
    new_username = profile.user.username if profile.user else None
    with conflict_on_duplicate("account_has_profile"):
        profile.save(update_fields=["user"])
        record(
            request.user,
            "driver.linked" if new_username else "driver.unlinked",
            "driver",
            profile.id,
            params={"driver": profile.display_name, "username": new_username or old_username},
            changes=[change("account", old_username, new_username)],
        )
    return profile


@router.get("/users", response=list[UserOut])
def list_users(request):
    require(manages_any_championship(request.user))
    return User.objects.filter(is_active=True).order_by("username")


class MergeIn(Schema):
    into_id: int
    reason: str = Field(min_length=1, max_length=500)


@router.post("/drivers/{driver_id}/merge", response=DriverOut)
def merge_driver(request, driver_id: int, payload: MergeIn):
    """Move everything of this profile to another profile of the same person, then delete it."""
    require(is_league_admin(request.user))
    old = get_object_or_404(DriverProfile, pk=driver_id)
    kept = get_object_or_404(DriverProfile, pk=payload.into_id)
    try:
        return merge(old, kept, request.user, payload.reason)
    except MergeError as error:
        raise HttpError(422, error.code) from error
