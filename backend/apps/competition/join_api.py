"""A driver joins a season. With free join on, the driver is entered at once. With it off, the
driver sends a request and an admin of the championship approves or declines it."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.audit.services import change, record
from apps.catalog.models import Car
from apps.common.api import require
from apps.identity.models import DriverProfile, User

from .api import _team_for, _visible_season
from .cars import allowed_car_ids, require_allowed
from .models import ChampionshipMember, JoinRequest, Season, SeasonEntry
from .permissions import can_manage

router = Router(tags=["competition"])


class JoinSeasonOut(Schema):
    season_id: int
    season_name: str
    championship_id: int
    championship_name: str
    free_join: bool
    # "entered", "pending" or "declined" when this driver already did something here.
    mine: str | None = None
    # The cars that the season allows. None: any car.
    car_ids: list[int] | None = None


class JoinOptionsOut(Schema):
    has_profile: bool
    seasons: list[JoinSeasonOut]


class JoinIn(Schema):
    car_id: int
    number: int = Field(ge=1, le=999)
    team: str = Field("", max_length=100)
    note: str = Field("", max_length=300)


class JoinOut(Schema):
    # "joined": entered at once. "requested": waiting for an admin.
    status: str
    entry_id: int | None = None
    request_id: int | None = None


class JoinRequestOut(Schema):
    id: int
    driver_name: str
    car_id: int
    car_name: str
    number: int
    team: str
    note: str
    created_at: str


class ApproveIn(Schema):
    # The admin can change the number when the one asked for is taken.
    number: int | None = Field(None, ge=1, le=999)


def _profile(user) -> DriverProfile | None:
    return DriverProfile.objects.filter(user=user).first()


def _managers(season: Season) -> set[int]:
    admins = ChampionshipMember.objects.filter(
        championship=season.championship, role=ChampionshipMember.Role.ADMIN
    ).values_list("user_id", flat=True)
    staff = User.objects.filter(is_staff=True, is_active=True).values_list("id", flat=True)
    return set(admins) | set(staff)


def _notify(user_ids, kind: str, season: Season, driver: DriverProfile) -> None:
    from apps.community.services import notify

    params = {
        "driver": driver.display_name,
        "season": season.name,
        "championship": season.championship.name,
    }
    notify(user_ids, kind, params, f"/seasons/{season.id}")


def _enter(
    season: Season, driver: DriverProfile, car: Car, number: int, team: str, actor
) -> SeasonEntry:
    """Create the entry, make the driver a driver of the championship, and write the audit."""
    if season.entries.filter(number=number).exists():
        raise HttpError(409, "number_taken")
    try:
        with transaction.atomic():
            entry = SeasonEntry.objects.create(
                season=season, driver=driver, car=car, number=number, team=team
            )
    except IntegrityError as error:
        raise HttpError(409, "entry_exists") from error
    if driver.user_id:
        ChampionshipMember.objects.get_or_create(
            championship=season.championship,
            user_id=driver.user_id,
            defaults={"role": ChampionshipMember.Role.DRIVER},
        )
    record(
        actor,
        "entry.created",
        "season",
        season.id,
        championship=season.championship,
        params={
            "season": season.name,
            "driver": driver.display_name,
            "number": entry.number,
            "car": car.name,
        },
        changes=[change("number", None, entry.number), change("team", None, entry.team)],
    )
    return entry


@router.get("/join/seasons", response=JoinOptionsOut)
def join_options(request):
    """The seasons that the driver of this account can join or ask to join."""
    profile = _profile(request.user)
    if profile is None:
        return JoinOptionsOut(has_profile=False, seasons=[])
    entered = set(profile.entries.values_list("season_id", flat=True))
    asked = {r.season_id: r.status for r in profile.join_requests.order_by("created_at")}
    seasons = Season.objects.select_related("championship").order_by(
        "championship__name", "-created_at"
    )
    rows = []
    for season in seasons:
        if season.id in entered:
            mine = "entered"
        elif asked.get(season.id) in (JoinRequest.Status.PENDING, JoinRequest.Status.DECLINED):
            mine = asked[season.id]
        else:
            mine = None
        rows.append(
            JoinSeasonOut(
                season_id=season.id,
                season_name=season.name,
                championship_id=season.championship_id,
                championship_name=season.championship.name,
                free_join=season.free_join,
                mine=mine,
                car_ids=allowed_car_ids(season),
            )
        )
    return JoinOptionsOut(has_profile=True, seasons=rows)


@router.post("/seasons/{season_id}/join", response={201: JoinOut})
def join_season(request, season_id: int, payload: JoinIn):
    """Free join: enter the season now. Otherwise: send a request for an admin."""
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    profile = _profile(request.user)
    if profile is None:
        raise HttpError(422, "no_driver_profile")
    if season.entries.filter(driver=profile).exists():
        raise HttpError(409, "entry_exists")
    car = get_object_or_404(Car, pk=payload.car_id)
    require_allowed(season, car)
    team = _team_for(season, payload.team)
    if season.free_join:
        entry = _enter(season, profile, car, payload.number, team, request.user)
        return Status(201, JoinOut(status="joined", entry_id=entry.id))
    if profile.join_requests.filter(season=season, status=JoinRequest.Status.PENDING).exists():
        raise HttpError(409, "request_pending")
    with transaction.atomic():
        join = JoinRequest.objects.create(
            season=season,
            driver=profile,
            car=car,
            number=payload.number,
            team=team,
            note=payload.note.strip(),
        )
        record(
            request.user,
            "join.requested",
            "season",
            season.id,
            championship=season.championship,
            params={
                "season": season.name,
                "driver": profile.display_name,
                "number": join.number,
                "car": car.name,
            },
        )
        _notify(_managers(season), "join.requested", season, profile)
    return Status(201, JoinOut(status="requested", request_id=join.id))


@router.get("/seasons/{season_id}/join-requests", response=list[JoinRequestOut])
def join_requests(request, season_id: int):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    pending = season.join_requests.filter(status=JoinRequest.Status.PENDING).select_related(
        "driver", "car"
    )
    return [
        JoinRequestOut(
            id=r.id,
            driver_name=r.driver.display_name,
            car_id=r.car_id,
            car_name=r.car.name,
            number=r.number,
            team=r.team,
            note=r.note,
            created_at=r.created_at.isoformat(),
        )
        for r in pending
    ]


def _pending(request, request_id: int) -> JoinRequest:
    join = get_object_or_404(
        JoinRequest.objects.select_related("season__championship", "driver__user", "car"),
        pk=request_id,
    )
    require(can_manage(request.user, join.season.championship))
    if join.status != JoinRequest.Status.PENDING:
        raise HttpError(409, "request_decided")
    return join


@router.post("/join-requests/{request_id}/approve", response=JoinOut)
def approve_join(request, request_id: int, payload: ApproveIn):
    join = _pending(request, request_id)
    with transaction.atomic():
        entry = _enter(
            join.season,
            join.driver,
            join.car,
            payload.number or join.number,
            join.team,
            request.user,
        )
        join.status = JoinRequest.Status.APPROVED
        join.decided_at = timezone.now()
        join.decided_by = request.user
        join.save(update_fields=["status", "decided_at", "decided_by"])
        _notify([join.driver.user_id], "join.approved", join.season, join.driver)
    return JoinOut(status="joined", entry_id=entry.id)


@router.post("/join-requests/{request_id}/decline", response=JoinOut)
def decline_join(request, request_id: int):
    join = _pending(request, request_id)
    with transaction.atomic():
        join.status = JoinRequest.Status.DECLINED
        join.decided_at = timezone.now()
        join.decided_by = request.user
        join.save(update_fields=["status", "decided_at", "decided_by"])
        record(
            request.user,
            "join.declined",
            "season",
            join.season_id,
            championship=join.season.championship,
            params={"season": join.season.name, "driver": join.driver.display_name},
        )
        _notify([join.driver.user_id], "join.declined", join.season, join.driver)
    return JoinOut(status="declined")
