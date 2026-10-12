from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.competition.models import Round
from apps.competition.permissions import can, can_view
from apps.rules.scoring import ResultError

from .ac_results import ResultFileError
from .lap_services import round_laps
from .models import ResultImport
from .penalty_services import apply as apply_logs
from .penalty_services import preview as penalty_preview
from .penalty_services import upload_log
from .real_penalty import PenaltyLogError
from .services import apply, link_guid, preview, upload

router = Router(tags=["imports"])


class MatchedOut(Schema):
    position: int
    guid: str
    name: str
    car_model: str
    laps: int
    total_time_ms: int
    best_lap_ms: int | None
    ballast_kg: int
    restrictor: int
    entry_id: int | None
    driver_name: str | None
    warnings: list[str]


class PreviewOut(Schema):
    session_type: str
    track: str
    layout: str
    attempt: int | None
    drivers: list[MatchedOut]
    unmatched: list[MatchedOut]
    missing: list[str]
    warnings: list[str]


class ImportOut(Schema):
    id: int
    filename: str
    sha256: str
    session_type: str
    status: str
    uploaded_by: str | None
    uploaded_at: datetime
    applied_at: datetime | None
    is_new: bool = False
    preview: PreviewOut | None = None


class GuidLinkIn(Schema):
    guid: str
    entry_id: int


class ApplyIn(Schema):
    statuses: dict[int, str] = {}
    ignored_guids: list[str] = []


def _round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    if not can(user, round_.season.championship, "results"):
        raise HttpError(403, "forbidden")
    return round_


def _import(user, import_id: int) -> ResultImport:
    result_import = get_object_or_404(ResultImport, pk=import_id)
    _round(user, result_import.round_id)
    return result_import


def _out(result_import: ResultImport, *, with_preview: bool, is_new: bool = False) -> ImportOut:
    return ImportOut(
        id=result_import.id,
        filename=result_import.filename,
        sha256=result_import.sha256,
        session_type=result_import.session_type,
        status=result_import.status,
        uploaded_by=result_import.uploaded_by.username if result_import.uploaded_by else None,
        uploaded_at=result_import.uploaded_at,
        applied_at=result_import.applied_at,
        is_new=is_new,
        preview=PreviewOut(**vars(preview(result_import))) if with_preview else None,
    )


def _run(action):
    try:
        return action()
    except (ResultFileError, ResultError) as error:
        raise HttpError(422, error.code) from error


@router.get("/rounds/{round_id}/imports", response=list[ImportOut])
def list_imports(request, round_id: int):
    round_ = _round(request.user, round_id)
    return [_out(i, with_preview=False) for i in round_.imports.select_related("uploaded_by")]


@router.post("/rounds/{round_id}/imports", response={200: ImportOut, 201: ImportOut})
def create_import(request, round_id: int, file: File[UploadedFile]):
    """Upload a result file. The same file again gives the stored import and adds nothing."""
    round_ = _round(request.user, round_id)
    content = file.read()
    result_import, is_new = _run(lambda: upload(round_, file.name, content, request.user))
    out = _run(lambda: _out(result_import, with_preview=True, is_new=is_new))
    return Status(201 if is_new else 200, out)


@router.get("/imports/{import_id}", response=ImportOut)
def get_import(request, import_id: int):
    result_import = _import(request.user, import_id)
    return _run(lambda: _out(result_import, with_preview=True))


@router.post("/imports/{import_id}/link", response=ImportOut)
def link(request, import_id: int, payload: GuidLinkIn):
    result_import = _import(request.user, import_id)
    _run(lambda: link_guid(result_import, payload.guid, payload.entry_id, request.user))
    return _run(lambda: _out(result_import, with_preview=True))


@router.post("/imports/{import_id}/apply", response=ImportOut)
def apply_import(request, import_id: int, payload: ApplyIn):
    result_import = _import(request.user, import_id)
    _run(
        lambda: apply(
            result_import,
            request.user,
            statuses=payload.statuses,
            ignored=payload.ignored_guids,
        )
    )
    result_import.refresh_from_db()
    return _run(lambda: _out(result_import, with_preview=True))


# Real Penalty logs


class PlannedStartOut(Schema):
    filename: str
    seconds: int
    new: bool


class PlannedPenaltyOut(Schema):
    key: str
    kind: str
    guid: str
    name: str
    entry_id: int | None
    driver_name: str | None
    penalty: str
    cause: str
    lap: int | None
    seconds: int
    already: bool


class PlannedLapOut(Schema):
    guid: str
    name: str
    lap_time_ms: int
    lap_id: int | None


class PenaltyLogOut(Schema):
    id: int
    filename: str
    session_type: str
    started_at: datetime
    ended_at: datetime
    status: str


class PenaltyLogsOut(Schema):
    files: list[PenaltyLogOut]
    new_files: int = 0
    logs: int
    final_log: str | None
    starts: list[PlannedStartOut]
    existing_restarts: int
    penalties: list[PlannedPenaltyOut]
    ignored_penalties: int
    invalid_laps: list[PlannedLapOut]
    warnings: list[str]


class ApplyLogsIn(Schema):
    penalty_keys: list[str] = []


def _logs_out(round_: Round, new_files: int = 0) -> PenaltyLogsOut:
    view = penalty_preview(round_)
    data = {key: value for key, value in vars(view).items()}
    return PenaltyLogsOut(
        files=[PenaltyLogOut.from_orm(f) for f in round_.penalty_logs.all()],
        new_files=new_files,
        **data,
    )


def _run_logs(action):
    try:
        return action()
    except (PenaltyLogError, ResultError) as error:
        raise HttpError(422, error.code) from error


@router.get("/rounds/{round_id}/penalty-logs", response=PenaltyLogsOut)
def list_penalty_logs(request, round_id: int):
    round_ = _round(request.user, round_id)
    return _run_logs(lambda: _logs_out(round_))


@router.post("/rounds/{round_id}/penalty-logs", response=PenaltyLogsOut)
def upload_penalty_logs(request, round_id: int, files: File[list[UploadedFile]]):
    """Upload one or more Real Penalty logs. A file that the round already has adds nothing."""
    round_ = _round(request.user, round_id)
    new = 0
    for item in files:
        content = item.read()
        _, is_new = _run_logs(
            lambda item=item, content=content: upload_log(round_, item.name, content, request.user)
        )
        new += int(is_new)
    return _run_logs(lambda: _logs_out(round_, new))


@router.post("/rounds/{round_id}/penalty-logs/apply", response=PenaltyLogsOut)
def apply_penalty_logs(request, round_id: int, payload: ApplyLogsIn):
    round_ = _round(request.user, round_id)
    _run_logs(lambda: apply_logs(round_, request.user, penalty_keys=payload.penalty_keys))
    return _run_logs(lambda: _logs_out(round_))


# Lap tables


class MarkedLapOut(Schema):
    lap_number: int
    time_ms: int
    sectors_ms: list[int]
    valid: bool
    cuts: int
    invalid_reason: str
    tyre: str
    pit: str | None
    time_mark: str | None
    sector_marks: list[str | None]


class AverageOut(Schema):
    ms: int | None
    laps: int
    excluded: dict[str, int]


class DriverLapsOut(Schema):
    entry_id: int
    driver_name: str
    number: int
    best_lap_ms: int | None
    best_lap_number: int | None
    average: AverageOut
    clean_average: AverageOut
    theoretical_ms: int | None
    best_sectors_ms: list[int | None]
    laps: list[MarkedLapOut]


class RoundLapsOut(Schema):
    session: str
    sessions: list[str]
    has_sectors: bool
    has_pit_data: bool
    clean_rules: list[str]
    drivers: list[DriverLapsOut]


@router.get("/rounds/{round_id}/laps", response=RoundLapsOut)
def get_laps(request, round_id: int, session: Literal["race", "qualifying", "practice"] = "race"):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    data = round_laps(round_, session)
    return RoundLapsOut(
        session=data.session,
        sessions=data.sessions,
        has_sectors=data.has_sectors,
        has_pit_data=data.has_pit_data,
        clean_rules=data.clean_rules,
        drivers=[
            DriverLapsOut(
                entry_id=info.entry_id,
                driver_name=info.driver_name,
                number=info.number,
                best_lap_ms=laps.best_lap_ms,
                best_lap_number=laps.best_lap_number,
                average=AverageOut(**vars(laps.average)),
                clean_average=AverageOut(**vars(laps.clean_average)),
                theoretical_ms=laps.theoretical_ms,
                best_sectors_ms=laps.best_sectors_ms,
                laps=[
                    MarkedLapOut(
                        **{k: v for k, v in vars(lap.row).items()},
                        valid=lap.row.valid,
                        time_mark=lap.time_mark,
                        sector_marks=lap.sector_marks,
                    )
                    for lap in laps.laps
                ],
            )
            for info, laps in data.drivers
        ],
    )
