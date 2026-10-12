from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema
from ninja.errors import HttpError
from pydantic import AwareDatetime

from apps.competition.models import ChampionshipMember, Round, Season, SeasonEntry
from apps.competition.permissions import can_manage, can_view
from apps.dashboard.services import my_handicap
from apps.reports.services import auto_request
from apps.rules.models import RulesVersion
from apps.rules.scoring import Line, ResultError, Status

from .models import Penalty, Protest, RaceResult, ResultVersion
from .services import (
    add_penalty,
    approve_result,
    decide_protest,
    protest_deadline,
    save_result,
    season_standings,
    submit_protest,
    title_scenarios,
)

router = Router(tags=["results"])


# Schemas


class RulesOut(Schema):
    version: int
    points_by_position: list[int]
    pole_bonus: int
    fastest_lap_bonus: int


class EntryOption(Schema):
    entry_id: int
    driver_id: int
    number: int
    driver_name: str
    car_name: str


class LineIn(Schema):
    entry_id: int
    status: Status
    position: int | None = Field(None, ge=1, le=200)
    pole: bool = False
    fastest_lap: bool = False


class LineOut(LineIn):
    number: int
    driver_name: str
    points: int
    entered_status: Status
    entered_position: int | None


class ResultIn(Schema):
    lines: list[LineIn]
    reason: str = Field("", max_length=500)


class VersionOut(Schema):
    number: int
    kind: str
    reason: str
    created_at: datetime
    created_by: str | None


class PenaltyOut(Schema):
    id: int
    entry_id: int
    driver_name: str
    kind: str
    value: int
    reason: str
    source: str
    attempt: int | None
    protest_id: int | None
    created_by: str | None
    created_at: datetime


class ProtestOut(Schema):
    id: int
    attempt: int | None
    submitted_by: str | None
    involved: list[str]
    lap: int | None
    description: str
    status: str
    decision: str
    decided_by: str | None
    created_at: datetime


class MyHandicapOut(Schema):
    entry_number: int
    car_name: str
    ballast_kg: int
    restrictor_pct: int
    source: str


class BriefingOut(Schema):
    announced_conditions: dict
    protest_window_minutes: int
    my_handicap: MyHandicapOut | None


class RoundDetail(Schema):
    id: int
    number: int
    season_id: int
    season_name: str
    championship_name: str
    track_name: str
    layout_name: str
    scheduled_at: AwareDatetime | None
    event_timezone: str
    can_manage: bool
    can_protest: bool
    briefing: BriefingOut
    rules: RulesOut
    entries: list[EntryOption]
    status: str | None
    published_at: datetime | None
    protest_deadline: datetime | None
    protest_window_open: bool
    approved_at: datetime | None
    version: int | None
    result: list[LineOut] | None
    versions: list[VersionOut]
    penalties: list[PenaltyOut]
    protests: list[ProtestOut]


class PenaltyIn(Schema):
    entry_id: int
    kind: Penalty.Kind
    value: int = Field(0, ge=0, le=200)
    reason: str = Field(max_length=500)


class ProtestIn(Schema):
    description: str = Field(max_length=2000)
    entry_ids: list[int] = []
    lap: int | None = Field(None, ge=0, le=999)


class PenaltyChoice(Schema):
    entry_id: int
    kind: Penalty.Kind
    value: int = Field(0, ge=0, le=200)


class DecisionIn(Schema):
    outcome: Protest.State
    decision: str = Field(max_length=2000)
    penalty: PenaltyChoice | None = None


class RoundScoreOut(Schema):
    round_number: int
    status: str | None
    position: int | None
    points: int
    official: bool


class StandingOut(Schema):
    rank: int
    entry_id: int
    number: int
    driver_name: str
    car_name: str
    team: str
    points: int
    wins: int
    rounds: list[RoundScoreOut]


STATUS_ORDER = {Status.FINISHED: 0, Status.DNF: 0, Status.DSQ: 1, Status.DNS: 2}


# Helpers


def _visible_round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship__league", "track_layout__track"),
        pk=round_id,
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _require_manage(user, round_: Round) -> None:
    if not can_manage(user, round_.season.championship):
        raise HttpError(403, "forbidden")


def _result_of(round_: Round) -> RaceResult:
    result = RaceResult.objects.filter(round=round_).first()
    if result is None:
        raise HttpError(422, "no_result")
    return result


def _username(user) -> str | None:
    return user.username if user else None


def _window_open(result: RaceResult | None) -> bool:
    if result is None or result.status == RaceResult.State.OFFICIAL:
        return False
    deadline = protest_deadline(result)
    return deadline is None or timezone.now() <= deadline


def _can_protest(user, round_: Round, result: RaceResult | None) -> bool:
    if not _window_open(result):
        return False
    is_member = ChampionshipMember.objects.filter(
        championship=round_.season.championship, user=user
    ).exists()
    return is_member or can_manage(user, round_.season.championship)


def _lines(version: ResultVersion) -> list[LineOut]:
    rows = sorted(
        version.lines.select_related("entry__driver"),
        key=lambda r: (STATUS_ORDER[Status(r.status)], r.position or 0, r.entry.number),
    )
    return [
        LineOut(
            entry_id=r.entry_id,
            status=r.status,
            position=r.position,
            pole=r.pole,
            fastest_lap=r.fastest_lap,
            number=r.entry.number,
            driver_name=r.entry.driver.display_name,
            points=r.points,
            entered_status=r.entered_status,
            entered_position=r.entered_position,
        )
        for r in rows
    ]


def _round_detail(user, round_: Round) -> RoundDetail:
    season = round_.season
    mine = my_handicap(user, round_)
    result = (
        RaceResult.objects.filter(round=round_)
        .select_related("current_version__rules_version")
        .first()
    )
    version = result.current_version if result else None
    rules = version.rules_version if version else RulesVersion.current_for(season)
    entries = season.entries.select_related("driver", "car")
    versions = result.versions.select_related("created_by").order_by("-number") if result else []
    penalties = (
        result.penalties.select_related("entry__driver", "attempt", "created_by") if result else []
    )
    protests = (
        result.protests.select_related("attempt", "submitted_by", "decided_by").prefetch_related(
            "involved__driver"
        )
        if result
        else []
    )
    return RoundDetail(
        id=round_.id,
        number=round_.number,
        season_id=season.id,
        season_name=season.name,
        championship_name=season.championship.name,
        track_name=round_.track_layout.track.name,
        layout_name=round_.track_layout.name,
        scheduled_at=round_.scheduled_at,
        event_timezone=season.championship.league.timezone,
        can_manage=can_manage(user, season.championship),
        can_protest=_can_protest(user, round_, result),
        briefing=BriefingOut(
            announced_conditions=round_.announced_conditions,
            protest_window_minutes=season.protest_window_minutes,
            my_handicap=MyHandicapOut(**vars(mine))
            if (mine := my_handicap(user, round_))
            else None,
        ),
        rules=RulesOut(
            version=rules.number,
            points_by_position=rules.points_by_position,
            pole_bonus=rules.pole_bonus,
            fastest_lap_bonus=rules.fastest_lap_bonus,
        ),
        entries=[
            EntryOption(
                entry_id=e.id,
                driver_id=e.driver_id,
                number=e.number,
                driver_name=e.driver.display_name,
                car_name=e.car.name,
            )
            for e in entries
        ],
        status=result.status if result else None,
        published_at=result.published_at if result else None,
        protest_deadline=protest_deadline(result) if result else None,
        protest_window_open=_window_open(result),
        approved_at=result.approved_at if result else None,
        version=version.number if version else None,
        result=_lines(version) if version else None,
        versions=[
            VersionOut(
                number=v.number,
                kind=v.kind,
                reason=v.reason,
                created_at=v.created_at,
                created_by=_username(v.created_by),
            )
            for v in versions
        ],
        penalties=[
            PenaltyOut(
                id=p.id,
                entry_id=p.entry_id,
                driver_name=p.entry.driver.display_name,
                kind=p.kind,
                value=p.value,
                reason=p.reason,
                source=p.source,
                attempt=p.attempt.number if p.attempt else None,
                protest_id=p.protest_id,
                created_by=_username(p.created_by),
                created_at=p.created_at,
            )
            for p in penalties
        ],
        protests=[
            ProtestOut(
                id=p.id,
                attempt=p.attempt.number if p.attempt else None,
                submitted_by=_username(p.submitted_by),
                involved=[e.driver.display_name for e in p.involved.all()],
                lap=p.lap,
                description=p.description,
                status=p.status,
                decision=p.decision,
                decided_by=_username(p.decided_by),
                created_at=p.created_at,
            )
            for p in protests
        ],
    )


def _run(action):
    try:
        return action()
    except ResultError as error:
        raise HttpError(422, error.code) from error


# Endpoints


@router.get("/rounds/{round_id}", response=RoundDetail)
def get_round(request, round_id: int):
    return _round_detail(request.user, _visible_round(request.user, round_id))


@router.get("/rounds/{round_id}/result/versions/{number}", response=list[LineOut])
def get_version(request, round_id: int, number: int):
    """The lines of an old version. Old versions stay for the history."""
    round_ = _visible_round(request.user, round_id)
    version = get_object_or_404(ResultVersion, result__round=round_, number=number)
    return _lines(version)


@router.put("/rounds/{round_id}/result", response=RoundDetail)
def put_result(request, round_id: int, payload: ResultIn):
    """Enter or correct the race classification. Each save makes a new version."""
    round_ = _visible_round(request.user, round_id)
    _require_manage(request.user, round_)
    lines = [
        Line(line.entry_id, line.status, line.position, line.pole, line.fastest_lap)
        for line in payload.lines
    ]
    _run(lambda: save_result(round_, lines, request.user, payload.reason))
    return _round_detail(request.user, round_)


@router.post("/rounds/{round_id}/result/approve", response=RoundDetail)
def approve(request, round_id: int):
    round_ = _visible_round(request.user, round_id)
    _require_manage(request.user, round_)
    result = _result_of(round_)
    _run(lambda: approve_result(result, request.user))
    # The report is extra. It runs in the worker, so it cannot block the approval.
    auto_request(round_, request.user)
    return _round_detail(request.user, round_)


@router.post("/rounds/{round_id}/penalties", response=RoundDetail)
def create_penalty(request, round_id: int, payload: PenaltyIn):
    round_ = _visible_round(request.user, round_id)
    _require_manage(request.user, round_)
    result = _result_of(round_)
    entry = get_object_or_404(SeasonEntry, pk=payload.entry_id)
    _run(
        lambda: add_penalty(
            result, entry, payload.kind, payload.value, payload.reason, request.user
        )
    )
    return _round_detail(request.user, round_)


@router.post("/rounds/{round_id}/protests", response=RoundDetail)
def create_protest(request, round_id: int, payload: ProtestIn):
    round_ = _visible_round(request.user, round_id)
    result = _result_of(round_)
    if not _can_protest(request.user, round_, result):
        # Give the exact reason when the result or the window blocks the protest.
        if result.status == RaceResult.State.OFFICIAL:
            raise HttpError(422, "result_is_official")
        deadline = protest_deadline(result)
        if deadline and timezone.now() > deadline:
            raise HttpError(422, "protest_window_closed")
        raise HttpError(403, "forbidden")
    _run(
        lambda: submit_protest(
            result,
            request.user,
            description=payload.description,
            entry_ids=payload.entry_ids,
            lap=payload.lap,
        )
    )
    return _round_detail(request.user, round_)


@router.post("/protests/{protest_id}/decision", response=RoundDetail)
def decide(request, protest_id: int, payload: DecisionIn):
    protest = get_object_or_404(
        Protest.objects.select_related("result__round__season__championship"), pk=protest_id
    )
    round_ = _visible_round(request.user, protest.result.round_id)
    _require_manage(request.user, round_)
    if payload.outcome == Protest.State.OPEN:
        raise HttpError(422, "outcome_required")
    penalty = payload.penalty.dict() if payload.penalty else None
    _run(
        lambda: decide_protest(
            protest,
            request.user,
            outcome=payload.outcome,
            decision=payload.decision,
            penalty=penalty,
        )
    )
    return _round_detail(request.user, round_)


class TitleDriverOut(Schema):
    entry_id: int
    driver_name: str
    points: int
    best_case: int
    status: str
    own_destiny: bool


class TitleOut(Schema):
    planned_rounds: int
    rounds_with_result: int
    remaining_rounds: int
    max_per_round: int
    max_if_not_winner: int
    leader_id: int | None
    leader_target: int | None
    drivers: list[TitleDriverOut]
    limits: list[str]


@router.get("/seasons/{season_id}/title", response=TitleOut)
def get_title(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    data = title_scenarios(season)
    names = {e.id: e.driver.display_name for e in season.entries.select_related("driver")}
    return TitleOut(
        planned_rounds=data.planned_rounds,
        rounds_with_result=data.rounds_with_result,
        remaining_rounds=data.scenarios.remaining_rounds,
        max_per_round=data.scenarios.max_per_round,
        max_if_not_winner=data.scenarios.max_if_not_winner,
        leader_id=data.scenarios.leader_id,
        leader_target=data.scenarios.leader_target,
        drivers=[
            TitleDriverOut(**vars(d), driver_name=names[d.entry_id]) for d in data.scenarios.drivers
        ],
        limits=data.limits,
    )


@router.get("/seasons/{season_id}/standings", response=list[StandingOut])
def get_standings(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    entries = {e.id: e for e in season.entries.select_related("driver", "car")}
    return [
        StandingOut(
            rank=row.rank,
            entry_id=row.entry_id,
            number=entries[row.entry_id].number,
            driver_name=entries[row.entry_id].driver.display_name,
            car_name=entries[row.entry_id].car.name,
            team=entries[row.entry_id].team,
            points=row.points,
            wins=row.wins,
            rounds=[RoundScoreOut(**vars(score)) for score in row.rounds],
        )
        for row in season_standings(season)
    ]
