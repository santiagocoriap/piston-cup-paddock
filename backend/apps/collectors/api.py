"""Collector endpoints. A collector signs in with its own key in the Authorization header.
The admin endpoints use the normal session."""

from datetime import datetime
from typing import Literal

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.security import HttpBearer
from pydantic import Field

from apps.competition.models import Championship, Round
from apps.competition.permissions import can, can_manage, can_view

from . import release
from .models import CollectorFile, CollectorToken
from .services import (
    CollectorError,
    assign,
    authenticate,
    create_token,
    key_matches,
    receive_events,
    receive_file,
    remember_version,
    revoke_token,
    save_status,
)

router = Router(tags=["collectors"])


class CollectorAuth(HttpBearer):
    def authenticate(self, request, token):
        found = authenticate(token)
        if found:
            remember_version(found, request.headers.get("User-Agent", ""))
        return found


# Collector side


class FileReceivedOut(Schema):
    id: int
    is_new: bool
    status: str
    round_id: int | None
    error: str


class EventIn(Schema):
    seq: int = Field(ge=0)
    kind: str = Field(max_length=30)
    at: datetime
    data: dict = {}


class EventsIn(Schema):
    run_id: str = Field(min_length=1, max_length=40)
    events: list[EventIn] = Field(max_length=500)


class EventsOut(Schema):
    new: int


class PingOut(Schema):
    collector: str
    championship: str


@router.get("/collector/ping", response=PingOut, auth=CollectorAuth())
def ping(request):
    token: CollectorToken = request.auth
    return PingOut(collector=token.name, championship=token.championship.name)


@router.post("/collector/files", response=FileReceivedOut, auth=CollectorAuth())
def upload_file(
    request,
    kind: Form[Literal["result", "penalty_log"]],
    file: File[UploadedFile],
):
    try:
        item, is_new = receive_file(request.auth, kind, file.name or "file", file.read())
    except CollectorError as error:
        raise HttpError(422, str(error)) from error
    return FileReceivedOut(
        id=item.id, is_new=is_new, status=item.status, round_id=item.round_id, error=item.error
    )


@router.post("/collector/events", response=EventsOut, auth=CollectorAuth())
def upload_events(request, payload: EventsIn):
    try:
        new = receive_events(
            request.auth, payload.run_id, [event.dict() for event in payload.events]
        )
    except CollectorError as error:
        raise HttpError(422, str(error)) from error
    return EventsOut(new=new)


class StatusIn(Schema):
    queued_files: int = Field(0, ge=0)
    last_error: str = Field("", max_length=500)
    last_error_at: datetime | None = None
    presets: list[dict] = Field(default_factory=list, max_length=50)
    current: str = Field("", max_length=100)


@router.post("/collector/status", auth=CollectorAuth())
def collector_status(request, payload: StatusIn):
    """The health of the collector, every 5 minutes: the files that wait, the last error, and
    the Content Manager presets."""
    save_status(request.auth, payload.queued_files, payload.last_error, payload.last_error_at)
    if payload.presets:
        from .server_setup import save_presets

        save_presets(request.auth, payload.presets, payload.current)
    return {"ok": True}


class CollectorVersionOut(Schema):
    # None: no release yet, or GitHub is not available. The collector asks again the next day.
    version: str | None
    sha256: str | None


@router.get("/collector/version", response=CollectorVersionOut, auth=CollectorAuth())
def collector_version(request):
    found = release.latest()
    return CollectorVersionOut(version=found and found.version, sha256=found and found.sha256)


@router.get("/collector/download", auth=CollectorAuth())
def collector_download(request):
    """The newest program, for the update of a collector."""
    found = release.latest()
    if found is None:
        raise HttpError(503, "no_release")
    try:
        data = release.program(found)
    except (OSError, release.ReleaseError) as error:
        raise HttpError(503, "no_release") from error
    response = HttpResponse(data, content_type="application/octet-stream")
    response["X-Paddock-Version"] = found.version
    return response


# Admin side


class CollectorIn(Schema):
    name: str = Field(min_length=1, max_length=60)


class CollectorOut(Schema):
    id: int
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked: bool
    files: int
    events: int


class CollectorCreatedOut(CollectorOut):
    key: str  # Shown one time only.


class CollectorFileOut(Schema):
    id: int
    collector: str
    kind: str
    filename: str
    session_type: str
    track: str
    session_time: datetime | None
    round_id: int | None
    status: str
    error: str
    received_at: datetime


class RoundChoiceOut(Schema):
    id: int
    season_name: str
    number: int
    track_name: str
    scheduled_at: datetime | None


class CollectorsOut(Schema):
    collectors: list[CollectorOut]
    rounds: list[RoundChoiceOut]  # The rounds an admin can choose for a file.
    files: list[CollectorFileOut]  # The newest files, and every file that needs a round.


class AssignIn(Schema):
    round_id: int


def _championship(user, championship_id: int) -> Championship:
    championship = get_object_or_404(Championship, pk=championship_id)
    if not can_view(user, championship):
        raise Http404
    if not can_manage(user, championship):
        raise HttpError(403, "forbidden")
    return championship


def _collector_out(token: CollectorToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "created_at": token.created_at,
        "last_seen_at": token.last_seen_at,
        "revoked": token.revoked_at is not None,
        "files": token.files.count(),
        "events": token.events.count(),
    }


def _file_out(item: CollectorFile) -> CollectorFileOut:
    return CollectorFileOut(
        id=item.id,
        collector=item.token.name,
        kind=item.kind,
        filename=item.filename,
        session_type=item.session_type,
        track=item.track,
        session_time=item.session_time,
        round_id=item.round_id,
        status=item.status,
        error=item.error,
        received_at=item.received_at,
    )


def _collectors_out(championship: Championship) -> CollectorsOut:
    files = CollectorFile.objects.filter(token__championship=championship).select_related("token")
    open_files = list(files.filter(status=CollectorFile.State.UNMATCHED))
    recent = [f for f in files[:20] if f.status != CollectorFile.State.UNMATCHED]
    rounds = Round.objects.filter(season__championship=championship).select_related(
        "season", "track_layout__track"
    )
    return CollectorsOut(
        collectors=[CollectorOut(**_collector_out(t)) for t in championship.collectors.all()],
        rounds=[
            RoundChoiceOut(
                id=r.id,
                season_name=r.season.name,
                number=r.number,
                track_name=r.track_layout.track.name,
                scheduled_at=r.scheduled_at,
            )
            for r in rounds.order_by("-season__created_at", "number")
        ],
        files=[_file_out(f) for f in open_files + recent],
    )


@router.get("/championships/{championship_id}/collectors", response=CollectorsOut)
def list_collectors(request, championship_id: int):
    return _collectors_out(_championship(request.user, championship_id))


@router.post("/championships/{championship_id}/collectors", response={201: CollectorCreatedOut})
def new_collector(request, championship_id: int, payload: CollectorIn):
    championship = _championship(request.user, championship_id)
    token, raw = create_token(championship, payload.name, request.user)
    return Status(201, CollectorCreatedOut(**_collector_out(token), key=raw))


class PackageIn(Schema):
    key: str = Field(min_length=1, max_length=200)


@router.post("/collectors/{collector_id}/package")
def collector_package(request, collector_id: int, payload: PackageIn):
    """ "Descargar colector": a zip with the program and a collector.ini with this key. The app
    keeps only a hash of the key, so the admin sends the key back (it shows one time only)."""
    token = get_object_or_404(CollectorToken, pk=collector_id)
    _championship(request.user, token.championship_id)
    if token.revoked_at is not None or not key_matches(token, payload.key):
        raise HttpError(422, "wrong_key")
    found = release.latest()
    if found is None:
        raise HttpError(503, "no_release")
    app_url = request.build_absolute_uri("/").rstrip("/")
    try:
        data = release.package(found, app_url, payload.key.strip())
    except (OSError, release.ReleaseError) as error:
        raise HttpError(503, "no_release") from error
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="paddock-collector.zip"'
    return response


@router.post("/collectors/{collector_id}/revoke", response=CollectorsOut)
def revoke(request, collector_id: int):
    token = get_object_or_404(CollectorToken, pk=collector_id)
    championship = _championship(request.user, token.championship_id)
    revoke_token(token, request.user)
    return _collectors_out(championship)


@router.post("/collector-files/{file_id}/assign", response=CollectorsOut)
def assign_file(request, file_id: int, payload: AssignIn):
    item = get_object_or_404(CollectorFile.objects.select_related("token"), pk=file_id)
    championship = get_object_or_404(Championship, pk=item.token.championship_id)
    if not can_view(request.user, championship):
        raise Http404
    if not can(request.user, championship, "results"):
        raise HttpError(403, "forbidden")
    round_ = get_object_or_404(Round.objects.select_related("season"), pk=payload.round_id)
    try:
        assign(item, round_, request.user)
    except CollectorError as error:
        raise HttpError(422, str(error)) from error
    return _collectors_out(championship)
