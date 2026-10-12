"""The collection health view and its retry actions."""

from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from procrastinate.contrib.django import app as worker_app
from procrastinate.contrib.django.models import ProcrastinateJob

from apps.competition.models import Championship
from apps.competition.permissions import can, can_manage, can_view, is_league_admin
from apps.reports.models import RaceReport
from apps.reports.services import ReportError, retry_report

from .health import championship_health

router = Router(tags=["health"])


class CollectorHealthOut(Schema):
    id: int
    name: str
    status: str
    last_seen_at: datetime | None
    last_file_at: datetime | None
    last_event_at: datetime | None


class RoundHealthOut(Schema):
    id: int
    number: int
    season_name: str
    track_name: str
    scheduled_at: datetime | None
    problems: list[str]
    counts: dict[str, int]


class FailedTaskOut(Schema):
    kind: str  # "report" or "job"
    id: int
    label: str
    error: str
    at: datetime | None


class HealthOut(Schema):
    collectors: list[CollectorHealthOut]
    rounds: list[RoundHealthOut]
    failed: list[FailedTaskOut]
    unmatched_files: int


def _failed_jobs() -> list[FailedTaskOut]:
    """Failed worker tasks. Only league admins see them, because a task can belong to any
    championship."""
    jobs = ProcrastinateJob.objects.filter(status="failed").order_by("-id")[:20]
    return [
        FailedTaskOut(
            kind="job",
            id=job.id,
            label=job.task_name,
            error=f"{job.attempts} attempts",
            at=job.scheduled_at,
        )
        for job in jobs
    ]


def _health(user, championship: Championship) -> HealthOut:
    data = championship_health(championship)
    failed = [FailedTaskOut(**vars(task)) for task in data.failed]
    if is_league_admin(user):
        failed += _failed_jobs()
    return HealthOut(
        collectors=[CollectorHealthOut(**vars(c)) for c in data.collectors],
        rounds=[RoundHealthOut(**vars(r)) for r in data.rounds],
        failed=failed,
        unmatched_files=data.unmatched_files,
    )


def _championship(user, championship_id: int) -> Championship:
    championship = get_object_or_404(Championship, pk=championship_id)
    if not can_view(user, championship):
        raise Http404
    if not can_manage(user, championship):
        raise HttpError(403, "forbidden")
    return championship


@router.get("/championships/{championship_id}/health", response=HealthOut)
def get_health(request, championship_id: int):
    return _health(request.user, _championship(request.user, championship_id))


@router.post("/reports/{report_id}/retry", response=HealthOut)
def retry_failed_report(request, report_id: int):
    report = get_object_or_404(
        RaceReport.objects.select_related("season__championship"), pk=report_id
    )
    championship = report.season.championship
    if not can_view(request.user, championship):
        raise Http404
    if not can(request.user, championship, "reports"):
        raise HttpError(403, "forbidden")
    try:
        retry_report(report, request.user)
    except ReportError as error:
        raise HttpError(422, str(error)) from error
    return _health(request.user, championship)


@router.post("/championships/{championship_id}/jobs/{job_id}/retry", response=HealthOut)
def retry_failed_job(request, championship_id: int, job_id: int):
    championship = _championship(request.user, championship_id)
    if not is_league_admin(request.user):
        raise HttpError(403, "forbidden")
    job = get_object_or_404(ProcrastinateJob, pk=job_id, status="failed")
    worker_app.job_manager.retry_job_by_id(job.id, retry_at=timezone.now())
    return _health(request.user, championship)
