from datetime import datetime
from typing import Literal

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile
from pydantic import AwareDatetime

from apps.collectors.incident_api import accepted_race_incidents
from apps.competition.models import ChampionshipMember, Round, Season, SeasonEntry
from apps.competition.permissions import can, can_manage, can_view, capabilities
from apps.dashboard.services import my_handicap
from apps.handicaps.services import handicap_checks
from apps.reports.services import auto_request
from apps.rules.models import RulesVersion
from apps.rules.scoring import Line, ResultError, Status

from .models import Penalty, Protest, ProtestEvidence, RaceResult, ResultVersion
from .services import (
    add_evidence,
    add_penalty,
    appeal_protest,
    approve_result,
    decide_appeal,
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
    driver_id: int
    driver_name: str
    laps: int | None = None
    total_ms: int | None = None
    gap_ms: int | None = None  # To the winner, on the same lap.
    laps_down: int | None = None  # Laps behind the winner.
    incidents: int | None = None  # None when the round has no collector events.
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


class EvidenceOut(Schema):
    id: int
    url: str
    filename: str
    content_type: str
    uploaded_by: str | None


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
    evidence: list[EvidenceOut] = []
    appeal_status: str = ""
    appeal_reason: str = ""
    appeal_decision: str = ""
    appeal_decided_by: str | None = None
    can_appeal: bool = False


class AppealIn(Schema):
    reason: str = Field(max_length=2000)


class AppealDecisionIn(Schema):
    outcome: Literal["upheld", "dismissed"]
    decision: str = Field(max_length=2000)


class MyHandicapOut(Schema):
    entry_number: int
    car_name: str
    ballast_kg: int
    restrictor_pct: int
    source: str


class HandicapCheckOut(Schema):
    entry_id: int
    driver_name: str
    assigned_kg: int
    assigned_pct: int
    observed_kg: int
    observed_pct: int


class BriefingOut(Schema):
    announced_conditions: dict
    protest_window_minutes: int
    restart_guidance: str
    first_lap_cutoff: str
    my_handicap: MyHandicapOut | None


class RoundDetail(Schema):
    id: int
    number: int
    season_id: int
    season_name: str
    championship_name: str
    track_name: str
    layout_name: str
    track_outline_url: str | None
    track_preview_url: str | None
    scheduled_at: AwareDatetime | None
    event_timezone: str
    can_manage: bool
    handicap_checks: list[HandicapCheckOut]
    capabilities: list[str]
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
    driver_id: int
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


def _require(user, round_: Round, capability: str) -> None:
    if not can(user, round_.season.championship, capability):
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


def _incident_counts(round_: Round) -> dict[str, int] | None:
    incidents, _, has_events = accepted_race_incidents(round_)
    if not has_events:
        return None
    counts: dict[str, int] = {}
    for incident in incidents:
        for car in incident.cars:
            counts[car] = counts.get(car, 0) + 1
    return counts


def _lines(version: ResultVersion) -> list[LineOut]:
    rows = sorted(
        version.lines.select_related("entry__driver"),
        key=lambda r: (STATUS_ORDER[Status(r.status)], r.position or 0, r.entry.number),
    )
    winner = next((r for r in rows if r.position == 1), None)
    counts = _incident_counts(version.result.round)

    def gap(row) -> tuple[int | None, int | None]:
        if winner is None or row.laps is None or winner.laps is None or row is winner:
            return None, None
        if row.laps < winner.laps:
            return None, winner.laps - row.laps
        if row.total_ms is None or winner.total_ms is None:
            return None, None
        return row.total_ms - winner.total_ms, None

    lines = [
        LineOut(
            entry_id=r.entry_id,
            status=r.status,
            position=r.position,
            pole=r.pole,
            fastest_lap=r.fastest_lap,
            number=r.entry.number,
            driver_id=r.entry.driver_id,
            driver_name=r.entry.driver.display_name,
            points=r.points,
            entered_status=r.entered_status,
            entered_position=r.entered_position,
            laps=r.laps,
            total_ms=r.total_ms,
            gap_ms=gap(r)[0],
            laps_down=gap(r)[1],
            incidents=(
                counts.get(r.entry.driver.steam_guid, 0)
                if counts is not None and r.entry.driver.steam_guid
                else None
            ),
        )
        for r in rows
    ]
    return lines


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
        track_outline_url=round_.track_layout.image_url("outline"),
        track_preview_url=round_.track_layout.image_url("preview"),
        scheduled_at=round_.scheduled_at,
        event_timezone=season.championship.league.timezone,
        can_manage=can_manage(user, season.championship),
        handicap_checks=[HandicapCheckOut(**vars(c)) for c in handicap_checks(round_)],
        capabilities=sorted(capabilities(user, season.championship)),
        can_protest=_can_protest(user, round_, result),
        briefing=BriefingOut(
            announced_conditions=round_.announced_conditions,
            protest_window_minutes=season.protest_window_minutes,
            restart_guidance=round_.track_layout.restart_guidance,
            first_lap_cutoff=round_.track_layout.first_lap_cutoff,
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
                evidence=[
                    EvidenceOut(
                        id=e.id,
                        url=e.url,
                        filename=e.filename,
                        content_type=e.content_type,
                        uploaded_by=_username(e.uploaded_by),
                    )
                    for e in p.evidence.select_related("uploaded_by")
                ],
                appeal_status=p.appeal_status,
                appeal_reason=p.appeal_reason,
                appeal_decision=p.appeal_decision,
                appeal_decided_by=_username(p.appeal_decided_by),
                can_appeal=(
                    p.submitted_by_id == user.id and p.status != "open" and not p.appeal_status
                ),
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
    _require(request.user, round_, "results")
    lines = [
        Line(line.entry_id, line.status, line.position, line.pole, line.fastest_lap)
        for line in payload.lines
    ]
    _run(lambda: save_result(round_, lines, request.user, payload.reason))
    return _round_detail(request.user, round_)


@router.post("/rounds/{round_id}/result/approve", response=RoundDetail)
def approve(request, round_id: int):
    round_ = _visible_round(request.user, round_id)
    _require(request.user, round_, "results")
    result = _result_of(round_)
    _run(lambda: approve_result(result, request.user))
    # The report is extra. It runs in the worker, so it cannot block the approval.
    auto_request(round_, request.user)
    return _round_detail(request.user, round_)


@router.post("/rounds/{round_id}/penalties", response=RoundDetail)
def create_penalty(request, round_id: int, payload: PenaltyIn):
    round_ = _visible_round(request.user, round_id)
    _require(request.user, round_, "penalties")
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
    _require(request.user, round_, "penalties")
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
            driver_id=entries[row.entry_id].driver_id,
            driver_name=entries[row.entry_id].driver.display_name,
            car_name=entries[row.entry_id].car.name,
            team=entries[row.entry_id].team,
            points=row.points,
            wins=row.wins,
            rounds=[RoundScoreOut(**vars(score)) for score in row.rounds],
        )
        for row in season_standings(season)
    ]


def _protest(user, protest_id: int):
    protest = get_object_or_404(
        Protest.objects.select_related("result__round__season__championship"), pk=protest_id
    )
    round_ = _visible_round(user, protest.result.round_id)
    return protest, round_


# A link, a file, or both. Ninja needs these defaults to read an optional multipart file.
NO_LINK = Form("")
NO_FILE = File(None)


@router.post("/protests/{protest_id}/evidence", response=RoundDetail)
def add_protest_evidence(
    request, protest_id: int, url: str = NO_LINK, file: UploadedFile = NO_FILE
):
    protest, round_ = _protest(request.user, protest_id)
    is_author = protest.submitted_by_id == request.user.id
    if not is_author and not can(request.user, round_.season.championship, "penalties"):
        raise HttpError(403, "forbidden")
    _run(lambda: add_evidence(protest, request.user, url=url.strip(), upload=file))
    return _round_detail(request.user, round_)


@router.get("/protest-evidence/{evidence_id}")
def evidence_file(request, evidence_id: int):
    """The file of a piece of evidence. Only members of the championship see it."""
    item = get_object_or_404(
        ProtestEvidence.objects.select_related("protest__result__round"), pk=evidence_id
    )
    _visible_round(request.user, item.protest.result.round_id)
    if not item.file:
        raise Http404
    response = FileResponse(
        item.file.open("rb"), filename=item.filename, content_type=item.content_type
    )
    # The type comes from the file bytes. These headers stop the browser from guessing
    # another type or running anything from the file.
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@router.post("/protests/{protest_id}/appeal", response=RoundDetail)
def appeal(request, protest_id: int, payload: AppealIn):
    protest, round_ = _protest(request.user, protest_id)
    _run(lambda: appeal_protest(protest, request.user, payload.reason))
    return _round_detail(request.user, round_)


@router.post("/protests/{protest_id}/appeal-decision", response=RoundDetail)
def appeal_decision(request, protest_id: int, payload: AppealDecisionIn):
    protest, round_ = _protest(request.user, protest_id)
    _require(request.user, round_, "penalties")
    _run(
        lambda: decide_appeal(
            protest, request.user, outcome=payload.outcome, decision=payload.decision
        )
    )
    return _round_detail(request.user, round_)
