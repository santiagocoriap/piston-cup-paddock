"""Endpoints of the Paddock script, and the race code page of the championship admin."""

from pathlib import Path

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import APIKeyHeader

from apps.audit.services import record
from apps.common.api import require
from apps.competition.models import Championship
from apps.competition.permissions import can_manage, can_view

from . import script
from .services import TelemetryError

router = Router(tags=["paddock script"])

SCRIPT_FILE = Path(__file__).resolve().parent / "lua" / "paddock.lua"
MAX_BODY = 4 * 1024 * 1024  # About 36,000 samples, a lap of 30 minutes.
SESSION_LABELS = {"practice": "Práctica", "qualifying": "Clasificación", "race": "Carrera"}


class ScriptAuth(APIKeyHeader):
    """The script signs in with the race code of the championship."""

    param_name = "X-Paddock-Code"

    def authenticate(self, request, key):
        return script.championship_for_code(key or "")


def _base_url(request: HttpRequest) -> str:
    return request.build_absolute_uri("/").rstrip("/")


@router.get("/script/paddock.lua", auth=None, include_in_schema=False)
def paddock_lua(request: HttpRequest):
    """The script for CSP. Every driver who joins the league server downloads it."""
    body = SCRIPT_FILE.read_text(encoding="utf-8").replace("__PADDOCK_URL__", _base_url(request))
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


class ScriptLapIn(Schema):
    steam_id: str
    track: str
    layout: str = ""
    car: str
    lap_number: int
    lap_time_ms: int
    valid: bool = True
    cuts: int = 0
    ended_at: int  # Seconds, from the clock of the driver PC.
    sent_at: int  # Seconds, from the same clock.
    samples: list[list[float]]


class ScriptLapOut(Schema):
    state: str  # "league", "pending", "rejected", or "known"
    # From the server, when the lap counts. The script shows them in AC.
    lap_number: int | None = None
    cuts: int | None = None


@router.post("/script/laps", response=ScriptLapOut, auth=ScriptAuth())
def script_lap(request: HttpRequest, payload: ScriptLapIn):
    if len(request.body) > MAX_BODY:
        raise HttpError(413, "lap_too_large")
    try:
        lap, state = script.receive_lap(request.auth, payload.dict())
    except TelemetryError as error:
        raise HttpError(422, str(error)) from error
    if lap is None or state not in ("league", "known"):
        return ScriptLapOut(state=state)
    return ScriptLapOut(state=state, lap_number=lap.lap_number, cuts=lap.cuts)


class NowOut(Schema):
    session_type: str | None = None
    round_number: int | None = None
    label: str = ""  # The text for the line in AC, in Spanish.


@router.get("/script/now", response=NowOut, auth=ScriptAuth())
def script_now(request: HttpRequest):
    now = script.now(request.auth)
    if now is None:
        return NowOut()
    parts = [f"Fecha {now.round_number}"] if now.round_number else []
    parts.append(SESSION_LABELS.get(now.session_type, now.session_type))
    return NowOut(
        session_type=now.session_type, round_number=now.round_number, label=" · ".join(parts)
    )


# Admin side


class ScriptSetupOut(Schema):
    script_url: str
    race_code: str
    created_at: str
    csp_section: str  # The text to paste in the CSP options of the server.


def _setup(request: HttpRequest, championship: Championship, code) -> ScriptSetupOut:
    url = f"{_base_url(request)}/api/script/paddock.lua"
    section = f"[SCRIPT_1]\nSCRIPT = '{url}'\nraceCode = '{code.code}'\n"
    return ScriptSetupOut(
        script_url=url,
        race_code=code.code,
        created_at=code.created_at.isoformat(),
        csp_section=section,
    )


def _managed(request: HttpRequest, championship_id: int) -> Championship:
    championship = get_object_or_404(Championship, pk=championship_id)
    if not can_view(request.user, championship):
        raise Http404
    require(can_manage(request.user, championship))
    return championship


@router.get("/championships/{championship_id}/script", response=ScriptSetupOut)
def script_setup(request: HttpRequest, championship_id: int):
    championship = _managed(request, championship_id)
    return _setup(request, championship, script.current_code(championship, request.user))


@router.post("/championships/{championship_id}/script/code", response=ScriptSetupOut)
def script_new_code(request: HttpRequest, championship_id: int):
    championship = _managed(request, championship_id)
    code = script.new_code(championship, request.user)
    record(
        request.user,
        "script.code_replaced",
        "championship",
        championship.id,
        championship=championship,
        params={"name": championship.name},
    )
    return _setup(request, championship, code)
