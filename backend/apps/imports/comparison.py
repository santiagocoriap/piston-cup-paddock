"""Compare two laps of one session: sectors always, and the delta along the track when both
laps have driver telemetry that the viewer may see."""

from dataclasses import dataclass, field

from apps.competition.models import Round
from apps.telemetry.models import TelemetryLap
from apps.telemetry.services import access, channels_for

from .delta import delta, speed_at
from .lap_services import _applied_import
from .models import ImportedLap

TELEMETRY_MATCH_MS = 50  # The Paddock script and the server can differ by a few ms.


class CompareError(ValueError):
    pass


@dataclass
class LapInfo:
    id: int
    entry_id: int
    driver_name: str
    lap_number: int
    lap_time_ms: int
    valid: bool
    sectors_ms: list[int]
    car: str
    ballast_kg: int
    restrictor: int
    tyre: str
    telemetry: str  # "full", "laps", "hidden" (exists, no access), or "none"


@dataclass
class Comparison:
    session: str
    choices: list[LapInfo] = field(default_factory=list)
    a: LapInfo | None = None
    b: LapInfo | None = None
    sector_diff_ms: list[int | None] = field(default_factory=list)
    delta: dict | None = None
    speed_a: dict | None = None
    speed_b: dict | None = None
    conditions: dict = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)


def _valid(lap: ImportedLap) -> bool:
    return lap.cuts == 0 and not lap.invalid_reason


def _telemetry(viewer, round_: Round, lap: ImportedLap) -> tuple[str, dict | None]:
    found = TelemetryLap.objects.filter(
        round=round_,
        driver=lap.entry.driver,
        lap_time_ms__gte=lap.lap_time_ms - TELEMETRY_MATCH_MS,
        lap_time_ms__lte=lap.lap_time_ms + TELEMETRY_MATCH_MS,
    ).select_related("driver", "round__season__championship")
    item = found.first()
    if item is None:
        return "none", None
    level = access(viewer, item)
    if not level:
        return "hidden", None
    return level, channels_for(item, level)


def _info(lap: ImportedLap, telemetry: str) -> LapInfo:
    return LapInfo(
        id=lap.id,
        entry_id=lap.entry_id,
        driver_name=lap.entry.driver.display_name,
        lap_number=lap.lap_number,
        lap_time_ms=lap.lap_time_ms,
        valid=_valid(lap),
        sectors_ms=list(lap.sectors_ms or []),
        car=lap.entry.car_name,
        ballast_kg=lap.ballast_kg,
        restrictor=lap.restrictor,
        tyre=lap.tyre,
        telemetry=telemetry,
    )


def _defaults(viewer, laps: list[ImportedLap]) -> tuple[ImportedLap, ImportedLap] | None:
    """The best valid lap of the viewer against the best valid lap of the session. Without a
    lap of the viewer: the two best valid laps of two different drivers."""
    valid = sorted((lap for lap in laps if _valid(lap)), key=lambda lap: lap.lap_time_ms)
    if len(valid) < 2:
        return None
    best = valid[0]
    driver = getattr(viewer, "driver_profile", None)
    mine = next((lap for lap in valid if driver and lap.entry.driver_id == driver.pk), None)
    if mine and mine.entry_id != best.entry_id:
        return mine, best
    other = next((lap for lap in valid if lap.entry_id != best.entry_id), None)
    if mine:  # The viewer has the session best. Compare with the best lap of another driver.
        return (mine, other) if other else None
    return (other, best) if other else None


def compare(viewer, round_: Round, session: str, a_id: int | None, b_id: int | None) -> Comparison:
    result = Comparison(session=session, conditions=round_.announced_conditions or {})
    result_import = _applied_import(round_, session)
    if result_import is None:
        result.gaps.append("no_laps")
        return result
    laps = list(
        ImportedLap.objects.filter(result_import=result_import, entry__isnull=False)
        .select_related("entry__driver", "entry__car")
        .order_by("lap_time_ms")
    )
    by_id = {lap.id: lap for lap in laps}
    result.choices = [_info(lap, "") for lap in laps if _valid(lap)]
    if a_id is not None or b_id is not None:
        if a_id not in by_id or b_id not in by_id:
            raise CompareError("lap_not_in_session")
        pair = (by_id[a_id], by_id[b_id])
    else:
        pair = _defaults(viewer, laps)
        if pair is None:
            result.gaps.append("not_enough_laps")
            return result
    lap_a, lap_b = pair
    level_a, channels_a = _telemetry(viewer, round_, lap_a)
    level_b, channels_b = _telemetry(viewer, round_, lap_b)
    result.a, result.b = _info(lap_a, level_a), _info(lap_b, level_b)

    count = min(len(result.a.sectors_ms), len(result.b.sectors_ms))
    result.sector_diff_ms = [result.b.sectors_ms[i] - result.a.sectors_ms[i] for i in range(count)]
    if not count:
        result.gaps.append("no_sectors")
    if channels_a and channels_b:
        result.delta = delta(channels_a, channels_b)
        result.speed_a = speed_at(channels_a)
        result.speed_b = speed_at(channels_b)
    if result.delta is None:
        result.gaps.append("no_telemetry")
    result.gaps.append("no_map")  # No layout has a map yet.
    if (lap_a.ballast_kg, lap_a.restrictor) != (lap_b.ballast_kg, lap_b.restrictor):
        result.gaps.append("different_handicaps")
    if lap_a.entry.car_id != lap_b.entry.car_id:
        result.gaps.append("different_cars")
    if lap_a.tyre != lap_b.tyre:
        result.gaps.append("different_tyres")
    return result
