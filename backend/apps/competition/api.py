from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from pydantic import AwareDatetime

from apps.audit.services import change, record
from apps.catalog.models import Car, TrackLayout
from apps.common.api import conflict_on_duplicate, require
from apps.common.timezones import DEFAULT_EVENT_TIMEZONE, is_timezone
from apps.identity.models import DriverProfile, User
from apps.rules.models import RulesVersion

from .calendar import fixed_layout_ids, next_round_number, voted_slots
from .models import Championship, ChampionshipMember, League, Round, Season, SeasonEntry
from .permissions import can_manage, can_view, is_league_admin, visible_championships

router = Router(tags=["competition"])


# Schemas


class NameIn(Schema):
    name: str = Field(min_length=1, max_length=100)


class LeagueIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(DEFAULT_EVENT_TIMEZONE, max_length=64)


class LeagueOut(Schema):
    id: int
    name: str
    timezone: str


class SeasonIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    planned_round_count: int = Field(ge=1, le=50)
    protest_window_minutes: int = Field(60, ge=0, le=10080)


class SeasonSettingsIn(Schema):
    protest_window_minutes: int | None = Field(None, ge=0, le=10080)
    allow_repeat_layouts: bool | None = None


class FixedRoundIn(Schema):
    track_layout_id: int
    number: int | None = Field(None, ge=1, le=99)
    scheduled_at: AwareDatetime | None = None


class ConditionsIn(Schema):
    time_of_day: str = Field("", max_length=20)
    weather: str = Field("", max_length=100)
    air_temp_c: int | None = Field(None, ge=-30, le=60)
    track_temp_c: int | None = Field(None, ge=-30, le=80)
    grip: str = Field("", max_length=50)
    notes: str = Field("", max_length=500)


class RoundPatchIn(Schema):
    number: int | None = Field(None, ge=1, le=99)
    scheduled_at: AwareDatetime | None = None
    announced_conditions: ConditionsIn | None = None


class SeasonSummary(Schema):
    id: int
    name: str
    planned_round_count: int
    protest_window_minutes: int
    allow_repeat_layouts: bool
    voted_slots: int


class ChampionshipOut(Schema):
    id: int
    name: str
    league_id: int
    league_name: str
    can_manage: bool


class ChampionshipDetail(ChampionshipOut):
    seasons: list[SeasonSummary]


class MemberIn(Schema):
    user_id: int
    role: ChampionshipMember.Role


class MemberOut(Schema):
    user_id: int
    username: str
    role: str


class EntryIn(Schema):
    driver_id: int
    car_id: int
    number: int = Field(ge=1, le=999)
    team: str = Field("", max_length=100)


class EntryOut(Schema):
    id: int
    driver_id: int
    driver_name: str
    car_id: int
    car_name: str
    number: int
    team: str


class RoundIn(Schema):
    track_layout_id: int
    scheduled_at: AwareDatetime
    number: int | None = Field(None, ge=1, le=99)


class RoundOut(Schema):
    id: int
    number: int
    track_layout_id: int
    track_name: str
    layout_name: str
    scheduled_at: AwareDatetime | None
    origin: str


class SeasonDetail(SeasonSummary):
    event_timezone: str
    championship_id: int
    championship_name: str
    can_manage: bool
    entries: list[EntryOut]
    rounds: list[RoundOut]


# Helpers


def _championship_out(user, championship: Championship) -> dict:
    return {
        "id": championship.id,
        "name": championship.name,
        "league_id": championship.league_id,
        "league_name": championship.league.name,
        "can_manage": can_manage(user, championship),
    }


def _visible_championship(user, championship_id: int) -> Championship:
    """Give 404, not 403, so a user cannot find championships outside their scope."""
    championship = get_object_or_404(
        Championship.objects.select_related("league"), pk=championship_id
    )
    if not can_view(user, championship):
        raise Http404
    return championship


def _visible_season(user, season_id: int) -> Season:
    season = get_object_or_404(Season.objects.select_related("championship__league"), pk=season_id)
    if not can_view(user, season.championship):
        raise Http404
    return season


def _entry_out(entry: SeasonEntry) -> EntryOut:
    return EntryOut(
        id=entry.id,
        driver_id=entry.driver_id,
        driver_name=entry.driver.display_name,
        car_id=entry.car_id,
        car_name=entry.car.name,
        number=entry.number,
        team=entry.team,
    )


def _round_out(round_: Round) -> RoundOut:
    return RoundOut(
        id=round_.id,
        number=round_.number,
        track_layout_id=round_.track_layout_id,
        track_name=round_.track_layout.track.name,
        layout_name=round_.track_layout.name,
        scheduled_at=round_.scheduled_at,
        origin=round_.origin,
    )


def _season_summary(season: Season) -> SeasonSummary:
    return SeasonSummary(
        id=season.id,
        name=season.name,
        planned_round_count=season.planned_round_count,
        protest_window_minutes=season.protest_window_minutes,
        allow_repeat_layouts=season.allow_repeat_layouts,
        voted_slots=voted_slots(season),
    )


def _season_detail(user, season: Season) -> SeasonDetail:
    entries = season.entries.select_related("driver", "car")
    rounds = season.rounds.select_related("track_layout__track")
    return SeasonDetail(
        id=season.id,
        name=season.name,
        planned_round_count=season.planned_round_count,
        protest_window_minutes=season.protest_window_minutes,
        allow_repeat_layouts=season.allow_repeat_layouts,
        voted_slots=voted_slots(season),
        event_timezone=season.championship.league.timezone,
        championship_id=season.championship_id,
        championship_name=season.championship.name,
        can_manage=can_manage(user, season.championship),
        entries=[_entry_out(e) for e in entries],
        rounds=[_round_out(r) for r in rounds],
    )


# Leagues and championships


@router.get("/leagues", response=list[LeagueOut])
def list_leagues(request):
    require(is_league_admin(request.user))
    return League.objects.order_by("name")


@router.post("/leagues", response={201: LeagueOut})
def create_league(request, payload: LeagueIn):
    require(is_league_admin(request.user))
    if not is_timezone(payload.timezone):
        raise HttpError(422, "bad_timezone")
    with conflict_on_duplicate("league_exists"):
        league = League.objects.create(name=payload.name, timezone=payload.timezone)
        record(request.user, "league.created", "league", league.id, params={"name": league.name})
    return Status(201, league)


@router.post("/leagues/{league_id}/championships", response={201: ChampionshipOut})
def create_championship(request, league_id: int, payload: NameIn):
    require(is_league_admin(request.user))
    league = get_object_or_404(League, pk=league_id)
    with conflict_on_duplicate("championship_exists"):
        championship = Championship.objects.create(league=league, name=payload.name)
        record(
            request.user,
            "championship.created",
            "championship",
            championship.id,
            championship=championship,
            params={"name": championship.name, "league": league.name},
        )
    return Status(201, _championship_out(request.user, championship))


@router.get("/championships", response=list[ChampionshipOut])
def list_championships(request):
    championships = visible_championships(request.user).select_related("league")
    return [_championship_out(request.user, c) for c in championships]


@router.get("/championships/{championship_id}", response=ChampionshipDetail)
def get_championship(request, championship_id: int):
    championship = _visible_championship(request.user, championship_id)
    return {
        **_championship_out(request.user, championship),
        "seasons": [_season_summary(s) for s in championship.seasons.all()],
    }


@router.get("/championships/{championship_id}/members", response=list[MemberOut])
def list_members(request, championship_id: int):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    members = championship.members.select_related("user").order_by("user__username")
    return [MemberOut(user_id=m.user_id, username=m.user.username, role=m.role) for m in members]


@router.put("/championships/{championship_id}/members", response=MemberOut)
def set_member(request, championship_id: int, payload: MemberIn):
    """Add a user to the championship, or change the role of a member."""
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    user = get_object_or_404(User, pk=payload.user_id)
    old = ChampionshipMember.objects.filter(championship=championship, user=user).first()
    with transaction.atomic():
        ChampionshipMember.objects.update_or_create(
            championship=championship, user=user, defaults={"role": payload.role}
        )
        record(
            request.user,
            "member.set",
            "championship",
            championship.id,
            championship=championship,
            params={"username": user.username, "role": payload.role},
            changes=[change("role", old.role if old else None, payload.role)],
        )
    return MemberOut(user_id=user.id, username=user.username, role=payload.role)


@router.post("/championships/{championship_id}/seasons", response={201: SeasonSummary})
def create_season(request, championship_id: int, payload: SeasonIn):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    with conflict_on_duplicate("season_exists"):
        season = Season.objects.create(championship=championship, **payload.dict())
        RulesVersion.current_for(season)  # Version 1 with the league defaults.
        record(
            request.user,
            "season.created",
            "season",
            season.id,
            championship=championship,
            params={"season": season.name, "championship": championship.name},
            changes=[
                change("name", None, season.name),
                change("planned_round_count", None, season.planned_round_count),
            ],
        )
    return Status(201, _season_summary(season))


# Seasons, entries, and rounds


@router.get("/seasons/{season_id}", response=SeasonDetail)
def get_season(request, season_id: int):
    season = _visible_season(request.user, season_id)
    return _season_detail(request.user, season)


@router.post("/seasons/{season_id}/entries", response={201: EntryOut})
def create_entry(request, season_id: int, payload: EntryIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    driver = get_object_or_404(DriverProfile, pk=payload.driver_id)
    car = get_object_or_404(Car, pk=payload.car_id)
    with conflict_on_duplicate("entry_exists"):
        entry = SeasonEntry.objects.create(
            season=season, driver=driver, car=car, number=payload.number, team=payload.team
        )
        record(
            request.user,
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
    return Status(201, _entry_out(entry))


@router.post("/seasons/{season_id}/rounds", response={201: RoundOut})
def create_round(request, season_id: int, payload: RoundIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    layout = get_object_or_404(
        TrackLayout.objects.select_related("track"), pk=payload.track_layout_id
    )
    number = payload.number or (season.rounds.count() + 1)
    with conflict_on_duplicate("round_number_exists"):
        round_ = Round.objects.create(
            season=season,
            number=number,
            track_layout=layout,
            scheduled_at=payload.scheduled_at,
            origin=Round.Origin.MANUAL,
        )
        round_.refresh_from_db()
        record(
            request.user,
            "round.created",
            "round",
            round_.id,
            championship=season.championship,
            params={"season": season.name, "number": number, "track": str(layout)},
            changes=[
                change("track_layout", None, str(layout)),
                change("scheduled_at", None, round_.scheduled_at.isoformat()),
            ],
        )
    return Status(201, _round_out(round_))


@router.patch("/seasons/{season_id}/settings", response=SeasonSummary)
def update_season_settings(request, season_id: int, payload: SeasonSettingsIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    changes = []
    for field in ("protest_window_minutes", "allow_repeat_layouts"):
        new = getattr(payload, field)
        if new is not None and new != getattr(season, field):
            changes.append(change(field, getattr(season, field), new))
            setattr(season, field, new)
    with transaction.atomic():
        season.save()
        record(
            request.user,
            "season.settings_changed",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name},
            changes=changes,
        )
    return _season_summary(season)


@router.post("/seasons/{season_id}/fixed-rounds", response={201: RoundOut})
def reserve_fixed_round(request, season_id: int, payload: FixedRoundIn):
    """Reserve a fixed track before the track voting. Position and date are optional."""
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    layout = get_object_or_404(
        TrackLayout.objects.select_related("track"), pk=payload.track_layout_id
    )
    fixed = season.rounds.filter(origin=Round.Origin.FIXED).count()
    if fixed + 1 > season.planned_round_count:
        raise HttpError(422, "too_many_fixed_rounds")
    if voted_slots(season) < 1:
        raise HttpError(422, "season_is_full")
    if layout.id in fixed_layout_ids(season):
        raise HttpError(409, "layout_already_fixed")
    number = payload.number or next_round_number(season)
    with conflict_on_duplicate("round_number_exists"):
        round_ = Round.objects.create(
            season=season,
            number=number,
            track_layout=layout,
            scheduled_at=payload.scheduled_at,
            origin=Round.Origin.FIXED,
        )
        round_.refresh_from_db()
        record(
            request.user,
            "round.fixed",
            "round",
            round_.id,
            championship=season.championship,
            params={"season": season.name, "number": number, "track": str(layout)},
            changes=[
                change("track_layout", None, str(layout)),
                change(
                    "scheduled_at",
                    None,
                    round_.scheduled_at.isoformat() if round_.scheduled_at else None,
                ),
            ],
        )
    return Status(201, _round_out(round_))


@router.patch("/rounds/{round_id}/calendar", response=RoundOut)
def update_round(request, round_id: int, payload: RoundPatchIn):
    """Set the calendar position or the date of a round."""
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(request.user, round_.season.championship):
        raise Http404
    require(can_manage(request.user, round_.season.championship))
    changes = []
    if payload.number is not None and payload.number != round_.number:
        changes.append(change("number", round_.number, payload.number))
        round_.number = payload.number
    if payload.scheduled_at is not None and payload.scheduled_at != round_.scheduled_at:
        old = round_.scheduled_at.isoformat() if round_.scheduled_at else None
        changes.append(change("scheduled_at", old, payload.scheduled_at.isoformat()))
        round_.scheduled_at = payload.scheduled_at
    if payload.announced_conditions is not None:
        conditions = payload.announced_conditions.dict()
        if conditions != round_.announced_conditions:
            changes.append(change("announced_conditions", round_.announced_conditions, conditions))
            round_.announced_conditions = conditions
    with conflict_on_duplicate("round_number_exists"):
        round_.save()
        record(
            request.user,
            "round.changed",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "season": round_.season.name,
                "number": round_.number,
                "track": str(round_.track_layout),
            },
            changes=changes,
        )
    round_.refresh_from_db()
    return _round_out(round_)
