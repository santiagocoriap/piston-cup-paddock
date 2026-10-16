from datetime import datetime
from typing import Literal

from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
from .conditions import DrawError, draw
from .models import (
    Championship,
    ChampionshipMember,
    ChampionshipRole,
    ConditionsPool,
    League,
    Round,
    RoundTrackChange,
    Season,
    SeasonEntry,
    Team,
)
from .permissions import can_manage, can_view, is_league_admin, visible_championships

router = Router(tags=["competition"])


# Schemas


class NameIn(Schema):
    name: str = Field(min_length=1, max_length=100)


class LeagueIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(DEFAULT_EVENT_TIMEZONE, max_length=64)


class LeagueChampionshipOut(Schema):
    id: int
    name: str
    season_count: int


class LeagueOut(Schema):
    id: int
    name: str
    timezone: str
    championships: list[LeagueChampionshipOut]

    @staticmethod
    def resolve_championships(league):
        # The list prefetches the championships with a season count. A new league has none.
        return [
            {"id": c.id, "name": c.name, "season_count": getattr(c, "season_count", 0)}
            for c in league.championships.all()
        ]


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
    provisional_reports: bool
    auto_publish_results: bool
    open_slots: int


class ChampionshipSettingsIn(Schema):
    """A missing setting keeps its value."""

    provisional_reports: bool | None = None
    auto_publish_results: bool | None = None
    open_slots: int | None = Field(None, ge=0, le=40)


class NextRoundBrief(Schema):
    round_id: int
    number: int
    track_name: str
    layout_name: str
    scheduled_at: datetime | None


class LatestSeasonOut(Schema):
    season_id: int
    name: str
    done: int  # Rounds with a result.
    total: int  # The planned number of rounds.
    next_round: NextRoundBrief | None
    leader: str | None  # The driver in first place, after the first points.


class ChampionshipDetail(ChampionshipOut):
    seasons: list[SeasonSummary]
    latest: LatestSeasonOut | None
    # The progress of each season, in the order of "seasons", for the season cards.
    progress: list[LatestSeasonOut]


class MemberIn(Schema):
    user_id: int
    role: ChampionshipMember.Role
    custom_role_id: int | None = None


class MemberOut(Schema):
    user_id: int
    username: str
    avatar_url: str | None = None
    role: str
    custom_role_id: int | None = None
    custom_role_name: str | None = None


Capability = Literal["results", "penalties", "restarts", "reports", "records"]


class RoleIn(Schema):
    name: str = Field(min_length=1, max_length=60)
    capabilities: list[Capability]


class RoleOut(Schema):
    id: int
    name: str
    capabilities: list[str]
    members: int


class EntryIn(Schema):
    driver_id: int
    car_id: int
    number: int = Field(ge=1, le=999)
    team: str = Field("", max_length=100)


class EntryOut(Schema):
    id: int
    driver_id: int
    driver_name: str
    avatar_url: str | None = None
    car_id: int
    car_name: str
    number: int
    team: str


class RoundIn(Schema):
    track_layout_id: int
    scheduled_at: AwareDatetime
    number: int | None = Field(None, ge=1, le=99)


class TrackChangeOut(Schema):
    old_layout: str
    new_layout: str
    reason: str
    changed_by: str | None
    changed_at: AwareDatetime


class ReasonIn(Schema):
    reason: str = Field(min_length=1, max_length=500)


class ReplaceTrackIn(ReasonIn):
    track_layout_id: int


class CloneIn(Schema):
    name: str = Field(min_length=1, max_length=100)


class RoundOut(Schema):
    id: int
    number: int
    track_layout_id: int
    track_name: str
    layout_name: str
    scheduled_at: AwareDatetime | None
    origin: str
    cancelled: bool
    cancel_reason: str
    track_changes: list[TrackChangeOut]
    # The conditions that an admin announced: time_of_day, weather, temperatures, grip, notes.
    announced_conditions: dict


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
        "provisional_reports": championship.provisional_reports,
        "auto_publish_results": championship.auto_publish_results,
        "open_slots": championship.open_slots,
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
        avatar_url=entry.driver.avatar_url(),
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
        cancelled=round_.cancelled_at is not None,
        cancel_reason=round_.cancel_reason,
        announced_conditions=round_.announced_conditions or {},
        track_changes=[
            TrackChangeOut(
                old_layout=str(c.old_layout),
                new_layout=str(c.new_layout),
                reason=c.reason,
                changed_by=c.changed_by.username if c.changed_by else None,
                changed_at=c.changed_at,
            )
            for c in round_.track_changes.select_related(
                "old_layout__track", "new_layout__track", "changed_by"
            )
        ],
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
    entries = season.entries.select_related("driver__user", "car")
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
    championships = Championship.objects.annotate(season_count=Count("seasons")).order_by("name")
    return League.objects.order_by("name").prefetch_related(
        Prefetch("championships", queryset=championships)
    )


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
    seasons = list(championship.seasons.all())
    progress = {s.id: _latest(s) for s in seasons}
    # The newest season. The list order can change, so the dates decide.
    newest = max(seasons, key=lambda s: (s.created_at, s.id)) if seasons else None
    return {
        **_championship_out(request.user, championship),
        "seasons": [_season_summary(s) for s in seasons],
        "latest": progress[newest.id] if newest else None,
        "progress": [progress[s.id] for s in seasons],
    }


def _latest(season: Season) -> LatestSeasonOut:
    """The progress of a season: rounds done, the next round, and the leader."""
    from apps.results.services import season_standings

    rounds = list(
        season.rounds.filter(cancelled_at__isnull=True)
        .select_related("track_layout__track", "result")
        .order_by("number")
    )
    done = [r for r in rounds if hasattr(r, "result")]
    upcoming = next((r for r in rounds if not hasattr(r, "result")), None)
    leader = None
    if done:
        table = season_standings(season)
        if table and table[0].points > 0:
            entry = SeasonEntry.objects.select_related("driver").get(pk=table[0].entry_id)
            leader = entry.driver.display_name
    return LatestSeasonOut(
        season_id=season.id,
        name=season.name,
        done=len(done),
        total=season.planned_round_count,
        next_round=NextRoundBrief(
            round_id=upcoming.id,
            number=upcoming.number,
            track_name=upcoming.track_layout.track.name,
            layout_name=upcoming.track_layout.name,
            scheduled_at=upcoming.scheduled_at,
        )
        if upcoming
        else None,
        leader=leader,
    )


@router.get("/championships/{championship_id}/members", response=list[MemberOut])
def list_members(request, championship_id: int):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    members = championship.members.select_related("user", "custom_role").order_by("user__username")
    return [_member_out(m) for m in members]


def _member_out(member: ChampionshipMember) -> MemberOut:
    return MemberOut(
        user_id=member.user_id,
        username=member.user.username,
        avatar_url=member.user.avatar_url(),
        role=member.role,
        custom_role_id=member.custom_role_id,
        custom_role_name=member.custom_role.name if member.custom_role else None,
    )


@router.patch("/championships/{championship_id}/settings", response=ChampionshipOut)
def championship_settings(request, championship_id: int, payload: ChampionshipSettingsIn):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    changes = []
    fields = []
    for name in ("provisional_reports", "auto_publish_results", "open_slots"):
        value = getattr(payload, name)
        if value is not None and value != getattr(championship, name):
            changes.append(change(name, getattr(championship, name), value))
            setattr(championship, name, value)
            fields.append(name)
    with transaction.atomic():
        if fields:
            championship.save(update_fields=fields)
            record(
                request.user,
                "championship.settings",
                "championship",
                championship.id,
                championship=championship,
                params={"name": championship.name},
                changes=changes,
            )
    return _championship_out(request.user, championship)


@router.put("/championships/{championship_id}/members", response=MemberOut)
def set_member(request, championship_id: int, payload: MemberIn):
    """Add a user to the championship, or change the role of a member."""
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    user = get_object_or_404(User, pk=payload.user_id)
    custom_role = None
    if payload.role == ChampionshipMember.Role.CUSTOM:
        # Only a role of this championship. A role of another championship gives a 404.
        custom_role = get_object_or_404(
            ChampionshipRole, pk=payload.custom_role_id, championship=championship
        )
    elif payload.custom_role_id is not None:
        raise HttpError(422, "custom_role_not_allowed")
    old = ChampionshipMember.objects.filter(championship=championship, user=user).first()
    with transaction.atomic():
        member, _ = ChampionshipMember.objects.update_or_create(
            championship=championship,
            user=user,
            defaults={"role": payload.role, "custom_role": custom_role},
        )
        record(
            request.user,
            "member.set",
            "championship",
            championship.id,
            championship=championship,
            params={"username": user.username, "role": _role_label(member)},
            changes=[change("role", _role_label(old) if old else None, _role_label(member))],
        )
    return _member_out(member)


def _role_label(member: ChampionshipMember) -> str:
    return member.custom_role.name if member.custom_role else member.role


def _role_out(role: ChampionshipRole) -> RoleOut:
    return RoleOut(
        id=role.id, name=role.name, capabilities=role.capabilities, members=role.members.count()
    )


@router.get("/championships/{championship_id}/roles", response=list[RoleOut])
def list_roles(request, championship_id: int):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    return [_role_out(role) for role in championship.roles.all()]


@router.post("/championships/{championship_id}/roles", response={201: RoleOut})
def create_role(request, championship_id: int, payload: RoleIn):
    championship = _visible_championship(request.user, championship_id)
    require(can_manage(request.user, championship))
    if championship.roles.filter(name=payload.name).exists():
        raise HttpError(422, "role_name_taken")
    with transaction.atomic():
        role = ChampionshipRole.objects.create(
            championship=championship,
            name=payload.name,
            capabilities=sorted(set(payload.capabilities)),
        )
        record(
            request.user,
            "role.created",
            "championship",
            championship.id,
            championship=championship,
            params={"name": role.name, "capabilities": ", ".join(role.capabilities)},
        )
    return Status(201, _role_out(role))


@router.put("/roles/{role_id}", response=RoleOut)
def update_role(request, role_id: int, payload: RoleIn):
    role = get_object_or_404(ChampionshipRole.objects.select_related("championship"), pk=role_id)
    championship = _visible_championship(request.user, role.championship_id)
    require(can_manage(request.user, championship))
    if championship.roles.filter(name=payload.name).exclude(pk=role.pk).exists():
        raise HttpError(422, "role_name_taken")
    old = ", ".join(role.capabilities)
    with transaction.atomic():
        role.name = payload.name
        role.capabilities = sorted(set(payload.capabilities))
        role.save(update_fields=["name", "capabilities"])
        record(
            request.user,
            "role.updated",
            "championship",
            championship.id,
            championship=championship,
            params={"name": role.name, "capabilities": ", ".join(role.capabilities)},
            changes=[change("capabilities", old, ", ".join(role.capabilities))],
        )
    return _role_out(role)


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


class TeamOut(Schema):
    id: int
    name: str


class TeamIn(Schema):
    name: str = Field(min_length=1, max_length=100)


def _team_for(season: Season, name: str) -> str:
    """The team name as the league has it. A new name becomes a team of the league."""
    name = " ".join(name.split())
    if not name:
        return ""
    league = season.championship.league
    team = league.teams.filter(name__iexact=name).first()
    return team.name if team else Team.objects.create(league=league, name=name).name


@router.get("/seasons/{season_id}/teams", response=list[TeamOut])
def season_teams(request, season_id: int):
    """The teams of the league of the season, for the entry form."""
    season = _visible_season(request.user, season_id)
    return season.championship.league.teams.all()


@router.post("/seasons/{season_id}/teams", response={201: TeamOut})
def create_team(request, season_id: int, payload: TeamIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    name = _team_for(season, payload.name)
    return Status(201, season.championship.league.teams.get(name=name))


@router.delete("/teams/{team_id}", response={204: None})
def delete_team(request, team_id: int):
    """A team leaves the list. Entries keep their team name."""
    team = get_object_or_404(Team.objects.select_related("league"), pk=team_id)
    championships = team.league.championships.all()
    require(any(can_manage(request.user, c) for c in championships))
    team.delete()
    return Status(204, None)


class EntryPatchIn(Schema):
    car_id: int | None = None
    number: int | None = Field(None, ge=1, le=999)
    team: str | None = Field(None, max_length=100)


@router.patch("/entries/{entry_id}", response=EntryOut)
def update_entry(request, entry_id: int, payload: EntryPatchIn):
    entry = get_object_or_404(
        SeasonEntry.objects.select_related("season__championship__league", "driver", "car"),
        pk=entry_id,
    )
    season = entry.season
    if not can_view(request.user, season.championship):
        raise Http404
    require(can_manage(request.user, season.championship))
    changes = []
    if payload.car_id is not None and payload.car_id != entry.car_id:
        car = get_object_or_404(Car, pk=payload.car_id)
        changes.append(change("car", entry.car.name, car.name))
        entry.car = car
    if payload.number is not None and payload.number != entry.number:
        changes.append(change("number", entry.number, payload.number))
        entry.number = payload.number
    if payload.team is not None:
        team = _team_for(season, payload.team)
        if team != entry.team:
            changes.append(change("team", entry.team, team))
            entry.team = team
    with conflict_on_duplicate("entry_exists"):
        entry.save()
        record(
            request.user,
            "entry.changed",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name, "driver": entry.driver.display_name},
            changes=changes,
        )
    return _entry_out(entry)


@router.post("/seasons/{season_id}/entries", response={201: EntryOut})
def create_entry(request, season_id: int, payload: EntryIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    driver = get_object_or_404(DriverProfile, pk=payload.driver_id)
    car = get_object_or_404(Car, pk=payload.car_id)
    payload.team = _team_for(season, payload.team)
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


class RoundOrderIn(Schema):
    round_ids: list[int] = Field(max_length=100)


@router.put("/seasons/{season_id}/round-order", response=list[RoundOut])
def order_rounds(request, season_id: int, payload: RoundOrderIn):
    """A new calendar order (drag and drop): round N is the Nth ID of the list. The list has
    every round of the season. The dates stay with their rounds."""
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    require(can_manage(request.user, season.championship))
    rounds = {r.id: r for r in season.rounds.select_related("track_layout__track")}
    if sorted(payload.round_ids) != sorted(rounds):
        raise HttpError(422, "round_list_mismatch")
    with transaction.atomic():
        # Two steps, so no two rounds have the same number on the way.
        for offset, round_id in enumerate(payload.round_ids, start=1):
            Round.objects.filter(pk=round_id).update(number=1000 + offset)
        for number, round_id in enumerate(payload.round_ids, start=1):
            Round.objects.filter(pk=round_id).update(number=number)
        record(
            request.user,
            "season.rounds_ordered",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name},
            changes=[
                change(
                    "order",
                    ", ".join(
                        str(rounds[i].track_layout)
                        for i in sorted(rounds, key=lambda i: rounds[i].number)
                    ),
                    ", ".join(str(rounds[i].track_layout) for i in payload.round_ids),
                )
            ],
        )
    ordered = season.rounds.select_related("track_layout__track").order_by("number")
    return [_round_out(r) for r in ordered]


def _managed_round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    require(can_manage(user, round_.season.championship))
    return round_


def _round_params(round_: Round) -> dict:
    return {
        "season": round_.season.name,
        "number": round_.number,
        "track": str(round_.track_layout),
    }


@router.post("/rounds/{round_id}/cancel", response=RoundOut)
def cancel_round(request, round_id: int, payload: ReasonIn):
    round_ = _managed_round(request.user, round_id)
    if round_.cancelled_at is not None:
        raise HttpError(422, "round_already_cancelled")
    with transaction.atomic():
        round_.cancelled_at = timezone.now()
        round_.cancel_reason = payload.reason
        round_.save(update_fields=["cancelled_at", "cancel_reason"])
        record(
            request.user,
            "round.cancelled",
            "round",
            round_.id,
            championship=round_.season.championship,
            params=_round_params(round_),
            reason=payload.reason,
        )
    return _round_out(round_)


@router.post("/rounds/{round_id}/restore", response=RoundOut)
def restore_round(request, round_id: int, payload: ReasonIn):
    round_ = _managed_round(request.user, round_id)
    if round_.cancelled_at is None:
        raise HttpError(422, "round_not_cancelled")
    with transaction.atomic():
        round_.cancelled_at = None
        round_.cancel_reason = ""
        round_.save(update_fields=["cancelled_at", "cancel_reason"])
        record(
            request.user,
            "round.restored",
            "round",
            round_.id,
            championship=round_.season.championship,
            params=_round_params(round_),
            reason=payload.reason,
        )
    return _round_out(round_)


@router.post("/rounds/{round_id}/replace-track", response=RoundOut)
def replace_track(request, round_id: int, payload: ReplaceTrackIn):
    """Put another track on a calendar round. A round with a result keeps its track."""
    round_ = _managed_round(request.user, round_id)
    if hasattr(round_, "result"):
        raise HttpError(422, "round_has_result")
    layout = get_object_or_404(
        TrackLayout.objects.select_related("track"), pk=payload.track_layout_id
    )
    if layout.id == round_.track_layout_id:
        raise HttpError(422, "same_track")
    old = round_.track_layout
    with transaction.atomic():
        RoundTrackChange.objects.create(
            round=round_,
            old_layout=old,
            new_layout=layout,
            reason=payload.reason,
            changed_by=request.user,
        )
        round_.track_layout = layout
        round_.save(update_fields=["track_layout"])
        record(
            request.user,
            "round.track_replaced",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={**_round_params(round_), "old": str(old)},
            changes=[change("track", str(old), str(layout))],
            reason=payload.reason,
        )
    return _round_out(round_)


@router.post("/seasons/{season_id}/clone", response={201: SeasonSummary})
def clone_season(request, season_id: int, payload: CloneIn):
    """A new season with the entries, the current rules, and the fixed tracks of this one.
    The fixed rounds keep their number and track, with no date."""
    source = _visible_season(request.user, season_id)
    require(can_manage(request.user, source.championship))
    rules = RulesVersion.current_for(source)
    with conflict_on_duplicate("season_exists"), transaction.atomic():
        season = Season.objects.create(
            championship=source.championship,
            name=payload.name,
            planned_round_count=source.planned_round_count,
            protest_window_minutes=source.protest_window_minutes,
            allow_repeat_layouts=source.allow_repeat_layouts,
        )
        RulesVersion.objects.create(
            season=season,
            number=1,
            reason=f"Copy of {source.name}",
            created_by=request.user,
            **{
                name: getattr(rules, name)
                for name in (
                    "points_by_position",
                    "pole_bonus",
                    "fastest_lap_bonus",
                    "ballast_steps",
                    "restrictor_steps",
                    "ballast_cap",
                    "restrictor_cap",
                    "ballast_reduction",
                    "restrictor_reduction",
                )
            },
        )
        SeasonEntry.objects.bulk_create(
            SeasonEntry(
                season=season, driver_id=e.driver_id, car_id=e.car_id, number=e.number, team=e.team
            )
            for e in source.entries.all()
        )
        Round.objects.bulk_create(
            Round(
                season=season,
                number=r.number,
                track_layout_id=r.track_layout_id,
                origin=Round.Origin.FIXED,
            )
            for r in source.rounds.filter(origin=Round.Origin.FIXED)
        )
        record(
            request.user,
            "season.cloned",
            "season",
            season.id,
            championship=source.championship,
            params={"season": season.name, "source": source.name},
        )
    return Status(201, _season_summary(season))


class PoolIn(Schema):
    weather: list[str] = Field(default_factory=list, max_length=20)
    time_of_day: list[str] = Field(default_factory=list, max_length=20)
    grip: list[str] = Field(default_factory=list, max_length=20)
    air_temp_min: int | None = Field(None, ge=-30, le=60)
    air_temp_max: int | None = Field(None, ge=-30, le=60)
    track_temp_min: int | None = Field(None, ge=-30, le=80)
    track_temp_max: int | None = Field(None, ge=-30, le=80)


class PoolOut(PoolIn):
    pass


class DrawIn(Schema):
    reason: str = Field("", max_length=500)


class DrawOut(Schema):
    values: dict
    reason: str
    drawn_by: str | None
    drawn_at: AwareDatetime


def _pool_out(season: Season) -> PoolOut:
    pool = ConditionsPool.objects.filter(season=season).first()
    if pool is None:
        return PoolOut()
    return PoolOut(**{name: getattr(pool, name) for name in PoolIn.model_fields})


@router.get("/seasons/{season_id}/conditions-pool", response=PoolOut)
def get_pool(request, season_id: int):
    return _pool_out(_visible_season(request.user, season_id))


@router.put("/seasons/{season_id}/conditions-pool", response=PoolOut)
def set_pool(request, season_id: int, payload: PoolIn):
    season = _visible_season(request.user, season_id)
    require(can_manage(request.user, season.championship))
    clean = {
        name: [v.strip()[:50] for v in getattr(payload, name) if v.strip()]
        for name in ("weather", "time_of_day", "grip")
    }
    fields = {**payload.dict(), **clean}
    with transaction.atomic():
        ConditionsPool.objects.update_or_create(season=season, defaults=fields)
        record(
            request.user,
            "season.conditions_pool",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name},
        )
    return _pool_out(season)


@router.get("/rounds/{round_id}/conditions-draws", response=list[DrawOut])
def list_draws(request, round_id: int):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    return [
        DrawOut(
            values=d.values,
            reason=d.reason,
            drawn_by=d.drawn_by.username if d.drawn_by else None,
            drawn_at=d.drawn_at,
        )
        for d in round_.conditions_draws.select_related("drawn_by")
    ]


@router.post("/rounds/{round_id}/draw-conditions", response=list[DrawOut])
def draw_conditions(request, round_id: int, payload: DrawIn):
    round_ = _managed_round(request.user, round_id)
    try:
        draw(round_, request.user, payload.reason)
    except DrawError as error:
        raise HttpError(422, error.code) from error
    return list_draws(request, round_id)
