from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer
from pydantic import Field

from apps.competition.models import Round
from apps.competition.permissions import can_view

from .engineer import MIN_LAPS, Trace, analyze, lap_length_m
from .models import TelemetryLap
from .services import (
    TelemetryError,
    access,
    authenticate,
    channels_for,
    create_key,
    receive_lap,
    sharing_for,
)

router = Router(tags=["telemetry"])


class DriverAuth(HttpBearer):
    def authenticate(self, request, token):
        return authenticate(token)


# Driver collector side


class LapIn(Schema):
    track: str = Field(max_length=200)
    car: str = Field(max_length=100)
    session_type: str = Field("", max_length=12)
    lap_number: int = Field(ge=0, le=999)
    lap_time_ms: int = Field(ge=0)
    valid: bool = True
    recorded_at: datetime
    sample_hz: int = Field(ge=1, le=100)
    channels: dict[str, list[float]]


class LapReceivedOut(Schema):
    id: int
    is_new: bool
    round_id: int | None


class CollectorStatusOut(Schema):
    driver: str
    laps: int


@router.get("/telemetry/status", response=CollectorStatusOut, auth=DriverAuth())
def collector_status(request):
    driver = request.auth.driver
    return CollectorStatusOut(driver=driver.display_name, laps=driver.laps.count())


@router.post("/telemetry/laps", response=LapReceivedOut, auth=DriverAuth())
def upload_lap(request, payload: LapIn):
    if payload.recorded_at.tzinfo is None:
        raise HttpError(422, "time_zone_required")
    try:
        lap, is_new = receive_lap(request.auth, payload.dict())
    except TelemetryError as error:
        raise HttpError(422, str(error)) from error
    return LapReceivedOut(id=lap.id, is_new=is_new, round_id=lap.round_id)


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
    has_key: bool
    last_seen_at: datetime | None
    laps: int
    last_lap_at: datetime | None
    sharing: SharingOut | None


class KeyOut(Schema):
    key: str  # Shown one time only.


def _driver(user):
    driver = getattr(user, "driver_profile", None)
    if driver is None:
        raise HttpError(422, "no_driver_profile")
    return driver


@router.get("/me/telemetry", response=MyTelemetryOut)
def my_telemetry(request):
    driver = getattr(request.user, "driver_profile", None)
    if driver is None:
        return MyTelemetryOut(
            has_driver=False,
            has_key=False,
            last_seen_at=None,
            laps=0,
            last_lap_at=None,
            sharing=None,
        )
    key = getattr(driver, "telemetry_key", None)
    sharing = sharing_for(driver)
    last = driver.laps.order_by("-uploaded_at").first()
    return MyTelemetryOut(
        has_driver=True,
        has_key=key is not None,
        last_seen_at=key.last_seen_at if key else None,
        laps=driver.laps.count(),
        last_lap_at=last.uploaded_at if last else None,
        sharing=SharingOut(
            teammates=sharing.teammates, drivers=sharing.drivers, admins=sharing.admins
        ),
    )


@router.post("/me/telemetry/key", response=KeyOut)
def new_key(request):
    return KeyOut(key=create_key(_driver(request.user)))


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


# Race engineer


class EngineerLapOut(Schema):
    id: int
    driver_name: str
    lap_number: int
    lap_time_ms: int
    own: bool


class AdviceOut(Schema):
    kind: str
    zone: int
    position: float
    reference_value: float
    lap_values: list[float]
    difference: float
    laps_showing: int
    laps_total: int


class EngineerOut(Schema):
    reference: EngineerLapOut | None
    laps: list[EngineerLapOut]
    lap_length_m: float | None
    zones: int
    advice: list[AdviceOut]
    setup_missing: list[str]  # Setup advice needs all of these. The app has none yet.
    gaps: list[str]


@router.get("/rounds/{round_id}/engineer", response=EngineerOut)
def engineer(request, round_id: int, session: Literal["race", "qualifying", "practice"] = "race"):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    driver = _driver(request.user)
    laps = round_.telemetry_laps.filter(session_type=session).select_related(
        "driver", "round__season__championship"
    )
    mine = [lap for lap in laps if lap.driver_id == driver.pk and lap.valid]
    visible = [lap for lap in laps.filter(valid=True) if access(request.user, lap)]
    reference = min(visible, key=lambda lap: lap.lap_time_ms, default=None)
    result = EngineerOut(
        reference=None,
        laps=[],
        lap_length_m=None,
        zones=0,
        advice=[],
        setup_missing=["setup", "tyre_temperatures", "fuel", "track_conditions"],
        gaps=[],
    )

    def out(lap) -> EngineerLapOut:
        return EngineerLapOut(
            id=lap.id,
            driver_name=lap.driver.display_name,
            lap_number=lap.lap_number,
            lap_time_ms=lap.lap_time_ms,
            own=lap.driver_id == driver.pk,
        )

    compared = [lap for lap in mine if reference is None or lap.pk != reference.pk]
    result.laps = [out(lap) for lap in compared]
    if reference is None or len(compared) < MIN_LAPS:
        result.gaps.append("not_enough_laps")
        return result
    result.reference = out(reference)
    reference_channels = channels_for(reference, access(request.user, reference))
    length = lap_length_m(
        reference_channels["pos"], reference_channels["t_ms"], reference_channels["speed_kmh"]
    )
    traces = []
    for lap in compared:
        channels = channels_for(lap, "full")
        traces.append(Trace.from_samples(channels["pos"], channels["speed_kmh"]))
    analysis = analyze(
        Trace.from_samples(reference_channels["pos"], reference_channels["speed_kmh"]),
        traces,
        length,
    )
    result.lap_length_m = round(length) if length else None
    result.zones = analysis.zones
    result.advice = [AdviceOut(**vars(item)) for item in analysis.advice]
    if not length:
        result.gaps.append("no_lap_length")
    return result
