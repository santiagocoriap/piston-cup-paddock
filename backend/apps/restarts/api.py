from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.competition.attempts import race_session
from apps.competition.models import Round
from apps.competition.permissions import can_manage, can_view

from .models import Restart
from .services import RestartError, record_restart, summarize, update_responsibility

router = Router(tags=["restarts"])


class RestartIn(Schema):
    lap: int | None = Field(None, ge=0, le=999)
    elapsed_seconds: int | None = Field(None, ge=0, le=86400)
    location: str = Field("", max_length=200)
    reason: Restart.Reason
    explanation: str = Field("", max_length=2000)
    requested_by_id: int | None = None
    executed_by_id: int | None = None
    responsibility: Restart.Responsibility = Restart.Responsibility.UNKNOWN
    driver_entry_ids: list[int] = []
    review_status: Restart.Review = Restart.Review.PENDING


class ResponsibilityIn(Schema):
    responsibility: Restart.Responsibility
    driver_entry_ids: list[int] = []
    review_status: Restart.Review
    reason: str = Field("", max_length=500)


class AttemptOut(Schema):
    number: int
    status: str


class ResponsibleOut(Schema):
    entry_id: int
    driver_name: str


class RestartOut(Schema):
    id: int
    abandoned_attempt: int
    replacement_attempt: int | None
    lap: int | None
    elapsed_seconds: int | None
    location: str
    reason: str
    explanation: str
    requested_by: str | None
    executed_by: str | None
    logged_by: str | None
    responsibility: str
    responsible: list[ResponsibleOut]
    review_status: str


class CausedOut(Schema):
    entry_id: int
    driver_name: str
    total: int
    shared: int


class SummaryOut(Schema):
    total: int
    caused: list[CausedOut]
    pending_or_disputed: int
    racing_incident: int
    technical: int
    unknown: int


class RoundRestartsOut(Schema):
    attempts: list[AttemptOut]
    restarts: list[RestartOut]
    summary: SummaryOut


def _round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _restart_out(restart: Restart) -> RestartOut:
    replacement = restart.replacement_attempt
    return RestartOut(
        id=restart.id,
        abandoned_attempt=restart.abandoned_attempt.number,
        replacement_attempt=replacement.number if replacement else None,
        lap=restart.lap,
        elapsed_seconds=restart.elapsed_seconds,
        location=restart.location,
        reason=restart.reason,
        explanation=restart.explanation,
        requested_by=restart.requested_by.display_name if restart.requested_by else None,
        executed_by=restart.executed_by.display_name if restart.executed_by else None,
        logged_by=restart.logged_by.username if restart.logged_by else None,
        responsibility=restart.responsibility,
        responsible=[
            ResponsibleOut(entry_id=e.id, driver_name=e.driver.display_name)
            for e in restart.responsible_entries.all()
        ],
        review_status=restart.review_status,
    )


def _round_restarts(round_: Round) -> RoundRestartsOut:
    session = race_session(round_)
    restarts = list(
        Restart.objects.filter(abandoned_attempt__session=session)
        .select_related(
            "abandoned_attempt", "replacement_attempt", "requested_by", "executed_by", "logged_by"
        )
        .prefetch_related("responsible_entries__driver")
    )
    summary = summarize(restarts)
    return RoundRestartsOut(
        attempts=[AttemptOut(number=a.number, status=a.status) for a in session.attempts.all()],
        restarts=[_restart_out(r) for r in restarts],
        summary=SummaryOut(
            total=summary.total,
            caused=[CausedOut(**vars(c)) for c in summary.caused],
            pending_or_disputed=summary.pending_or_disputed,
            racing_incident=summary.racing_incident,
            technical=summary.technical,
            unknown=summary.unknown,
        ),
    )


@router.get("/rounds/{round_id}/restarts", response=RoundRestartsOut)
def get_restarts(request, round_id: int):
    return _round_restarts(_round(request.user, round_id))


@router.post("/rounds/{round_id}/restarts", response={201: RoundRestartsOut})
def create_restart(request, round_id: int, payload: RestartIn):
    round_ = _round(request.user, round_id)
    if not can_manage(request.user, round_.season.championship):
        raise HttpError(403, "forbidden")
    fields = payload.dict(exclude={"driver_entry_ids"})
    try:
        record_restart(
            round_, request.user, responsible_entry_ids=payload.driver_entry_ids, **fields
        )
    except RestartError as error:
        raise HttpError(422, error.code) from error
    return Status(201, _round_restarts(round_))


@router.put("/restarts/{restart_id}/responsibility", response=RoundRestartsOut)
def set_responsibility(request, restart_id: int, payload: ResponsibilityIn):
    restart = get_object_or_404(
        Restart.objects.select_related("abandoned_attempt__session__round__season__championship"),
        pk=restart_id,
    )
    round_ = restart.abandoned_attempt.session.round
    if not can_view(request.user, round_.season.championship):
        raise Http404
    if not can_manage(request.user, round_.season.championship):
        raise HttpError(403, "forbidden")
    try:
        update_responsibility(
            restart,
            request.user,
            responsibility=payload.responsibility,
            entry_ids=payload.driver_entry_ids,
            review_status=payload.review_status,
            reason=payload.reason,
        )
    except RestartError as error:
        raise HttpError(422, error.code) from error
    return _round_restarts(round_)
