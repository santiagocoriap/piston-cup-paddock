"""The backup status for the health card, and the backup button. League admins only."""

from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.audit.services import record
from apps.competition.permissions import is_league_admin

from .models import BackupRun
from .tasks import backup

router = Router(tags=["backups"])


class BackupRunOut(Schema):
    status: str
    file_name: str
    size_bytes: int | None
    rows: int | None
    files: int | None
    error: str
    started_by: str | None
    started_at: datetime
    finished_at: datetime | None


class BackupStatusOut(Schema):
    last: BackupRunOut | None
    last_ok_at: datetime | None


def _require_admin(user) -> None:
    if not is_league_admin(user):
        raise HttpError(403, "forbidden")


def _out(run: BackupRun) -> BackupRunOut:
    return BackupRunOut(
        status=run.status,
        file_name=run.file_name,
        size_bytes=run.size_bytes,
        rows=run.rows,
        files=run.files,
        error=run.error,
        started_by=run.started_by.username if run.started_by else None,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _status() -> BackupStatusOut:
    last = BackupRun.objects.select_related("started_by").first()
    ok = BackupRun.objects.filter(status=BackupRun.Status.OK).first()
    return BackupStatusOut(
        last=_out(last) if last else None, last_ok_at=ok.finished_at if ok else None
    )


@router.get("/backups/status", response=BackupStatusOut)
def backup_status(request):
    _require_admin(request.user)
    return _status()


@router.post("/backups", response=BackupStatusOut)
def start_backup(request):
    _require_admin(request.user)
    if BackupRun.objects.filter(status=BackupRun.Status.RUNNING).exists():
        raise HttpError(409, "backup_running")
    run = BackupRun.objects.create(started_by=request.user)
    record(request.user, "backup.started", "backup", run.id)
    backup.defer(run_id=run.id)
    return _status()
