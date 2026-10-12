from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.competition.models import Round
from apps.competition.permissions import can_manage, can_view
from apps.rules.scoring import ResultError

from .ac_results import ResultFileError
from .models import ResultImport
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
    if not can_manage(user, round_.season.championship):
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
