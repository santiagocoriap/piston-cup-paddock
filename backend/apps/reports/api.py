from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.competition.models import Round
from apps.competition.permissions import can_manage, can_view

from .models import RaceReport
from .services import ReportError, ai_configured, mark_read, read_ids, request_report

router = Router(tags=["reports"])


class ReportOut(Schema):
    id: int
    number: int
    status: str
    language: str
    tone: str
    model: str
    prompt_version: str
    source_version: int | None
    result_status: str
    created_at: datetime
    generated_at: datetime | None
    text: str
    unread: bool
    error: str | None = None  # Admins only.
    facts: dict | None = None  # Admins only.


class ReportsOut(Schema):
    can_generate: bool
    ai_configured: bool
    reports: list[ReportOut]


class ReportIn(Schema):
    language: Literal["es", "en"] = "es"
    tone: Literal["friendly", "roast"] = "friendly"


class ReadOut(Schema):
    ok: bool


def _round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship__league", "track_layout__track"),
        pk=round_id,
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _reports_out(user, round_: Round) -> ReportsOut:
    admin = can_manage(user, round_.season.championship)
    reports = round_.reports.select_related("source_version")
    if not admin:
        reports = reports.filter(status=RaceReport.State.READY)
    reports = list(reports)
    read = read_ids(user, reports)
    return ReportsOut(
        can_generate=admin,
        ai_configured=ai_configured() if admin else False,
        reports=[
            ReportOut(
                id=r.id,
                number=r.number,
                status=r.status,
                language=r.language,
                tone=r.tone,
                model=r.model,
                prompt_version=r.prompt_version,
                source_version=r.source_version.number if r.source_version else None,
                result_status=r.result_status,
                created_at=r.created_at,
                generated_at=r.generated_at,
                text=r.text,
                unread=r.status == RaceReport.State.READY and r.id not in read,
                error=r.error if admin else None,
                facts=r.facts if admin else None,
            )
            for r in reports
        ],
    )


@router.get("/rounds/{round_id}/reports", response=ReportsOut)
def list_reports(request, round_id: int):
    return _reports_out(request.user, _round(request.user, round_id))


@router.post("/rounds/{round_id}/reports", response=ReportsOut)
def create_report(request, round_id: int, payload: ReportIn):
    round_ = _round(request.user, round_id)
    if not can_manage(request.user, round_.season.championship):
        raise HttpError(403, "forbidden")
    try:
        request_report(round_, request.user, language=payload.language, tone=payload.tone)
    except ReportError as error:
        raise HttpError(400, str(error)) from error
    return _reports_out(request.user, round_)


@router.post("/reports/{report_id}/read", response=ReadOut)
def read_report(request, report_id: int):
    report = get_object_or_404(
        RaceReport.objects.select_related("round__season__championship"),
        pk=report_id,
        status=RaceReport.State.READY,
    )
    if not can_view(request.user, report.round.season.championship):
        raise Http404
    mark_read(report, request.user)
    return ReadOut(ok=True)
