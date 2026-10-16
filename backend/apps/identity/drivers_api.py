from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.audit.services import change, record
from apps.common.api import conflict_on_duplicate, conflict_on_protected, require
from apps.competition.permissions import is_league_admin, manages_any_championship

from .merge import MergeError, merge
from .models import DriverProfile, User

router = Router(tags=["drivers"])


class DriverIn(Schema):
    display_name: str = Field(min_length=1, max_length=100)
    steam_guid: str | None = Field(None, pattern=r"^\d{17}$")


class DriverOut(Schema):
    id: int
    display_name: str
    steam_guid: str | None
    user_id: int | None
    username: str | None
    career_points: int = 0

    @staticmethod
    def resolve_username(profile: DriverProfile) -> str | None:
        return profile.user.username if profile.user else None


class LinkIn(Schema):
    user_id: int | None


class UserOut(Schema):
    id: int
    username: str


@router.get("/drivers", response=list[DriverOut])
def list_drivers(request):
    """Career points are the official points of all seasons."""
    from apps.results.services import career_points

    profiles = list(DriverProfile.objects.select_related("user"))
    totals = career_points([p.id for p in profiles])
    for profile in profiles:
        profile.career_points = totals[profile.id]
    return profiles


@router.post("/drivers", response={201: DriverOut})
def create_driver(request, payload: DriverIn):
    require(manages_any_championship(request.user))
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


@router.delete("/drivers/{driver_id}", response={204: None})
def delete_driver(request, driver_id: int):
    """Delete a driver profile. A driver with season entries stays: merge or keep the profile."""
    require(manages_any_championship(request.user))
    profile = get_object_or_404(DriverProfile, pk=driver_id)
    with conflict_on_protected("driver_in_use"):
        record(
            request.user,
            "driver.deleted",
            "driver",
            profile.id,
            params={"driver": profile.display_name},
        )
        profile.delete()
    return Status(204, None)
