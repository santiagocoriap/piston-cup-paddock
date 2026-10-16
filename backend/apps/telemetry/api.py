from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.competition.models import Round
from apps.competition.permissions import can_manage, can_view
from apps.identity.models import DriverProfile

from . import coach
from .models import EngineerNote, TelemetryLap
from .services import access, channels_for, sharing_for
from .track_map import track_map

router = Router(tags=["telemetry"])


# The driver in the app


Level = Literal["none", "laps", "full"]


class SharingIn(Schema):
    teammates: Level
    drivers: Level  # "full" shows the inputs to every driver: the driver chooses it.
    admins: Level


class SharingOut(SharingIn):
    pass


class MyTelemetryOut(Schema):
    has_driver: bool
    laps: int
    last_lap_at: datetime | None
    sharing: SharingOut | None


def _driver(user):
    driver = getattr(user, "driver_profile", None)
    if driver is None:
        raise HttpError(422, "no_driver_profile")
    return driver


@router.get("/me/telemetry", response=MyTelemetryOut)
def my_telemetry(request):
    driver = getattr(request.user, "driver_profile", None)
    if driver is None:
        return MyTelemetryOut(has_driver=False, laps=0, last_lap_at=None, sharing=None)
    sharing = sharing_for(driver)
    last = driver.laps.order_by("-uploaded_at").first()
    return MyTelemetryOut(
        has_driver=True,
        laps=driver.laps.count(),
        last_lap_at=last.uploaded_at if last else None,
        sharing=SharingOut(
            teammates=sharing.teammates, drivers=sharing.drivers, admins=sharing.admins
        ),
    )


@router.put("/me/telemetry/sharing", response=SharingOut)
def set_sharing(request, payload: SharingIn):
    sharing = sharing_for(_driver(request.user))
    sharing.teammates = payload.teammates
    sharing.drivers = payload.drivers
    sharing.admins = payload.admins
    sharing.save()
    return SharingOut(teammates=sharing.teammates, drivers=sharing.drivers, admins=sharing.admins)


# Viewers


class LapOut(Schema):
    id: int
    driver_name: str
    session_type: str
    lap_number: int
    lap_time_ms: int
    valid: bool
    access: str
    # The race start of the lap. None for a lap that no server session matched.
    attempt_number: int | None = None


class LapDetailOut(LapOut):
    sample_hz: int
    car: str
    channels: dict[str, list[float]]


def _lap_out(lap: TelemetryLap, level: str) -> dict:
    return {
        "id": lap.id,
        "driver_name": lap.driver.display_name,
        "session_type": lap.session_type,
        "lap_number": lap.lap_number,
        "lap_time_ms": lap.lap_time_ms,
        "valid": lap.valid,
        "access": level,
        "attempt_number": lap.attempt_number,
    }


@router.get("/rounds/{round_id}/telemetry", response=list[LapOut])
def round_telemetry(request, round_id: int):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    rows = []
    for lap in round_.telemetry_laps.select_related("driver", "round__season__championship"):
        level = access(request.user, lap)
        if level:
            rows.append(LapOut(**_lap_out(lap, level)))
    return rows


@router.get("/telemetry-laps/{lap_id}", response=LapDetailOut)
def lap_detail(request, lap_id: int):
    lap = get_object_or_404(
        TelemetryLap.objects.select_related("driver", "round__season__championship"), pk=lap_id
    )
    level = access(request.user, lap)
    if not level:
        raise Http404
    return LapDetailOut(
        **_lap_out(lap, level),
        sample_hz=lap.sample_hz,
        car=lap.car,
        channels=channels_for(lap, level),
    )


class TrackMapOut(Schema):
    # The length of the layout in meters, from the game files. None when unknown.
    length_m: int | None
    # The points of the track in lap order: the place on the lap (0 to 1), then x and z.
    spline: list[float]
    x: list[float]
    z: list[float]


@router.get("/rounds/{round_id}/track-map", response=TrackMapOut)
def round_track_map(request, round_id: int):
    """The track drawing of the round, from the collector positions, for the telemetry map."""
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout"), pk=round_id
    )
    if not can_view(request.user, round_.season.championship):
        raise Http404
    points = track_map(round_)
    return TrackMapOut(
        length_m=round_.track_layout.length_m,
        spline=[p[0] for p in points],
        x=[p[1] for p in points],
        z=[p[2] for p in points],
    )


# Race engineer


Session = Literal["race", "qualifying", "practice"]


class EngineerLapOut(Schema):
    id: int
    driver_name: str
    lap_number: int
    lap_time_ms: int


class MetricsOut(Schema):
    time_s: float | None
    brake_m: float | None
    brake_peak: float | None
    min_kmh: float | None
    apex_m: float | None
    throttle_m: float | None
    coast_m: float | None
    exit_kmh: float | None
    gear: int | None


class CauseOut(Schema):
    kind: str
    yours: float
    reference: float
    difference: float


class CornerOut(Schema):
    number: int
    start: float
    apex: float
    end: float
    loss_s: float | None
    reference_lap_id: int
    yours: MetricsOut
    reference: MetricsOut
    causes: list[CauseOut]


class SpreadOut(Schema):
    number: int
    time_s: float
    brake_m: float | None
    min_kmh: float | None
    best_s: float
    worst_s: float


class NoteOut(Schema):
    id: int
    status: str
    text: str
    error: str
    created_at: datetime


class DriverOptionOut(Schema):
    id: int
    name: str


class EngineerOut(Schema):
    driver: DriverOptionOut | None
    drivers: list[DriverOptionOut]  # Only for an admin: the drivers with telemetry laps.
    session: str
    laps: list[EngineerLapOut]  # The valid laps of the driver.
    lap: EngineerLapOut | None
    reference: EngineerLapOut | None  # None: the best corners of the driver.
    reference_options: list[EngineerLapOut]  # The best lap of each other driver.
    length_m: int | None
    has_pedals: bool
    ideal_s: float | None
    corners: list[CornerOut]
    spread: list[SpreadOut]
    note: NoteOut | None
    ai_available: bool
    gaps: list[str]


def _engineer_lap(lap: TelemetryLap | None) -> EngineerLapOut | None:
    if lap is None:
        return None
    return EngineerLapOut(
        id=lap.id,
        driver_name=lap.driver.display_name,
        lap_number=lap.lap_number,
        lap_time_ms=lap.lap_time_ms,
    )


def _note_out(note: EngineerNote | None) -> NoteOut | None:
    if note is None:
        return None
    return NoteOut(
        id=note.id,
        status=note.status,
        text=note.text,
        error=note.error,
        created_at=note.created_at,
    )


def _engineer_round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _engineer_driver(user, round_: Round, driver_id: int | None) -> DriverProfile | None:
    """The driver to coach: the user, or for an admin any driver of the round."""
    own = getattr(user, "driver_profile", None)
    if driver_id is None or (own is not None and own.pk == driver_id):
        return own
    if not can_manage(user, round_.season.championship):
        raise HttpError(403, "not_allowed")
    return get_object_or_404(DriverProfile, pk=driver_id)


def _pick(request, round_id, session, driver, lap, reference):
    round_ = _engineer_round(request.user, round_id)
    profile = _engineer_driver(request.user, round_, driver)
    return (
        round_,
        profile,
        (coach.pick(request.user, round_, profile, session, lap, reference) if profile else None),
    )


@router.get("/rounds/{round_id}/engineer", response=EngineerOut)
def engineer(
    request,
    round_id: int,
    session: Session = "race",
    driver: int | None = None,
    lap: int | None = None,
    reference: str | None = None,
):
    """Where the driver loses time in each corner, and why, against a reference lap."""
    round_, profile, picked = _pick(request, round_id, session, driver, lap, reference)
    drivers: list[DriverOptionOut] = []
    if can_manage(request.user, round_.season.championship):
        seen = {}
        for row in round_.telemetry_laps.filter(session_type=session).select_related("driver"):
            seen[row.driver_id] = row.driver.display_name
        drivers = [
            DriverOptionOut(id=k, name=v) for k, v in sorted(seen.items(), key=lambda i: i[1])
        ]
    result = EngineerOut(
        driver=DriverOptionOut(id=profile.pk, name=profile.display_name) if profile else None,
        drivers=drivers,
        session=session,
        laps=[],
        lap=None,
        reference=None,
        reference_options=[],
        length_m=None,
        has_pedals=False,
        ideal_s=None,
        corners=[],
        spread=[],
        note=None,
        ai_available=coach.reports.ai_configured(),
        gaps=[],
    )
    if profile is None:
        result.gaps.append("no_driver")
        return result
    if picked is None or picked.lap is None or picked.analysis is None:
        result.gaps.append("no_laps")
        return result
    analysis = picked.analysis
    result.laps = [_engineer_lap(item) for item in picked.laps]
    result.lap = _engineer_lap(picked.lap)
    result.reference = _engineer_lap(picked.reference)
    result.reference_options = [_engineer_lap(item) for item in picked.options]
    result.length_m = analysis.length_m
    result.has_pedals = analysis.has_pedals
    result.ideal_s = analysis.ideal_s
    result.corners = [
        CornerOut(
            number=c.number,
            start=c.start,
            apex=c.apex,
            end=c.end,
            loss_s=c.loss_s,
            reference_lap_id=c.reference_key,
            yours=MetricsOut(**vars(c.yours)),
            reference=MetricsOut(**vars(c.reference)),
            causes=[CauseOut(**vars(x)) for x in c.causes],
        )
        for c in analysis.corners
    ]
    result.spread = [SpreadOut(**vars(item)) for item in analysis.spread]
    result.note = _note_out(coach.latest_note(picked.lap, picked.reference))
    if picked.reference is None and len(picked.laps) < 2:
        result.gaps.append("one_lap")
    if not analysis.corners:
        result.gaps.append("no_corners")
    return result


class NoteIn(Schema):
    session: Session = "race"
    driver: int | None = None
    lap: int | None = None
    reference: str | None = None
    language: Literal["es", "en"] = "es"


@router.post("/rounds/{round_id}/engineer/note", response=NoteOut)
def engineer_note(request, round_id: int, payload: NoteIn):
    """Ask the AI for a coaching note from the numbers of the engineer."""
    round_, _, picked = _pick(
        request, round_id, payload.session, payload.driver, payload.lap, payload.reference
    )
    if picked is None or picked.lap is None or not picked.analysis or not picked.analysis.corners:
        raise HttpError(422, "no_laps")
    if not coach.reports.ai_configured():
        raise HttpError(422, "ai_not_configured")
    return _note_out(coach.request_note(picked, round_, request.user, payload.language))
