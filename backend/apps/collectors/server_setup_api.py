"""Endpoints of "Enviar al servidor": the preview and the push for the admin, and the commands
for the server collector."""

from datetime import datetime

from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from apps.common.urls import public_url
from apps.competition.models import Round
from apps.competition.permissions import can_manage, can_view

from . import server_setup
from .api import CollectorAuth
from .models import ServerPush

router = Router(tags=["server setup"])


class PushEntryOut(Schema):
    number: int
    name: str
    team: str
    guid: str
    model: str
    ballast_kg: int
    restrictor_pct: int


class PushOut(Schema):
    id: int
    status: str
    error: str
    requested_by: str | None
    requested_at: datetime
    finished_at: datetime | None
    collector: str | None


class PresetOut(Schema):
    folder: str
    name: str


class SetupOut(Schema):
    track: dict
    entries: list[PushEntryOut]
    conditions: dict
    warnings: list[str]
    open_slots: int
    # The Content Manager presets of the server. preset: the one that the collector uses now.
    presets: list[PresetOut]
    preset: str
    latest: PushOut | None
    has_collector: bool


def _push_out(item: ServerPush | None) -> PushOut | None:
    if item is None:
        return None
    return PushOut(
        id=item.id,
        status=item.status,
        error=item.error,
        requested_by=item.requested_by.username if item.requested_by else None,
        requested_at=item.requested_at,
        finished_at=item.finished_at,
        collector=item.collector.name if item.collector else None,
    )


def _managed_round(request: HttpRequest, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship__league", "track_layout__track"),
        pk=round_id,
    )
    if not can_view(request.user, round_.season.championship):
        raise Http404
    if not can_manage(request.user, round_.season.championship):
        raise HttpError(403, "forbidden")
    return round_


def _base_url(request: HttpRequest) -> str:
    return public_url(request)


def _setup_out(request: HttpRequest, round_: Round) -> SetupOut:
    try:
        content = server_setup.build(round_, _base_url(request))
    except server_setup.SetupError as error:
        raise HttpError(422, error.code) from error
    championship = round_.season.championship
    presets, preset = server_setup.server_presets(championship)
    return SetupOut(
        presets=presets,
        preset=preset,
        track=content["track"],
        entries=content["entries"],
        conditions=content["conditions"],
        warnings=content["warnings"],
        open_slots=content["open_slots"],
        latest=_push_out(round_.server_pushes.select_related("requested_by", "collector").first()),
        has_collector=championship.collectors.filter(revoked_at__isnull=True).exists(),
    )


@router.get("/rounds/{round_id}/server-setup", response=SetupOut)
def server_setup_preview(request: HttpRequest, round_id: int):
    """What "Enviar al servidor" would write, and the state of the last push."""
    return _setup_out(request, _managed_round(request, round_id))


class PushIn(Schema):
    # The free slots for this push only. None: the setting of the championship.
    open_slots: int | None = Field(None, ge=0, le=40)
    # The folder of the Content Manager preset. None: the preset that the collector uses.
    preset: str | None = Field(None, max_length=100)


@router.post("/rounds/{round_id}/server-push", response=SetupOut)
def server_push(request: HttpRequest, round_id: int, payload: PushIn | None = None):
    round_ = _managed_round(request, round_id)
    slots = payload.open_slots if payload else None
    preset = payload.preset if payload else None
    try:
        server_setup.push(round_, request.user, _base_url(request), slots, preset)
    except server_setup.SetupError as error:
        raise HttpError(422, error.code) from error
    return _setup_out(request, round_)


# Collector side


class CommandOut(Schema):
    id: int | None = None
    content: dict | None = None


class CommandReportIn(Schema):
    status: str  # "waiting", "done", or "failed"
    error: str = ""


@router.get("/collector/commands", response=CommandOut, auth=CollectorAuth())
def collector_command(request: HttpRequest):
    """The push that waits for the collector, or nothing."""
    item = server_setup.next_command(request.auth)
    if item is None:
        return CommandOut()
    return CommandOut(id=item.id, content=item.content)


@router.post("/collector/commands/{push_id}", response=PushOut, auth=CollectorAuth())
def collector_report(request: HttpRequest, push_id: int, payload: CommandReportIn):
    try:
        item = server_setup.report(request.auth, push_id, payload.status, payload.error)
    except server_setup.SetupError as error:
        raise HttpError(422, error.code) from error
    return _push_out(item)
