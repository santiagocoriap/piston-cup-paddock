"""Race engineer: driving advice from measured differences. Pure functions with no database.

The input is the speed trace of a reference lap and the speed traces of the driver's laps,
all against the normalized track position. Only speed is compared, because the reference lap
can belong to another driver, and other drivers never share their inputs.

The advice shows where the driver differs from the reference, not why. Each piece of advice
has its evidence and a test that the driver can try. A difference that shows on one lap only
gives no advice: it must repeat.
"""

from dataclasses import dataclass, field
from statistics import mean, pstdev

STEPS = 500  # Points along the lap.
WINDOW = 10  # Steps that a braking zone looks ahead (2 % of the lap).
MIN_DROP_KMH = 20  # A speed drop that starts a braking zone.
EARLY_M = 15  # Braking this much earlier than the reference counts.
SLOW_KMH = 5  # A minimum speed this much lower than the reference counts.
SPREAD_KMH = 6  # Exit speeds that spread more than this are inconsistent.
REPEAT_SHARE = 0.6  # The share of laps that must show the difference.
MIN_LAPS = 2


@dataclass
class Trace:
    """Speed at STEPS + 1 positions. None where the lap has no sample."""

    speed: list[float | None]

    @classmethod
    def from_samples(cls, pos: list[float], speed: list[float]) -> "Trace":
        points = []
        for p, v in zip(pos, speed, strict=False):
            if points and p <= points[-1][0]:
                continue
            if not points and p > 0.5:
                continue
            points.append((p, v))
        values: list[float | None] = []
        index = 0
        for step in range(STEPS + 1):
            target = step / STEPS
            while index < len(points) - 1 and points[index + 1][0] < target:
                index += 1
            if not points or target < points[0][0] or target > points[-1][0]:
                values.append(None)
                continue
            p0, v0 = points[index]
            p1, v1 = points[min(index + 1, len(points) - 1)]
            values.append(v0 if p1 == p0 else v0 + (v1 - v0) * (target - p0) / (p1 - p0))
        return cls(values)


def lap_length_m(pos: list[float], t_ms: list[float], speed: list[float]) -> float | None:
    """The lap length from speed and time. The app has no track length data yet."""
    total = 0.0
    for i in range(1, min(len(t_ms), len(speed))):
        if pos[i] > pos[i - 1]:
            total += speed[i - 1] / 3.6 * (t_ms[i] - t_ms[i - 1]) / 1000
    return total or None


@dataclass
class Zone:
    number: int
    start: int  # The step where the reference starts to brake.
    apex: int  # The step with the lowest reference speed.
    exit: int  # A step after the apex where the exit speed is measured.


def zones(reference: Trace) -> list[Zone]:
    speed = reference.speed
    found: list[Zone] = []
    step = 1
    while step < STEPS - WINDOW:
        here = speed[step]
        ahead = [v for v in speed[step : step + WINDOW] if v is not None]
        is_peak = here is not None and speed[step - 1] is not None and here >= speed[step - 1]
        if is_peak and ahead and here - min(ahead) >= MIN_DROP_KMH:
            end = min(step + WINDOW * 4, STEPS)
            window = [(speed[i], i) for i in range(step, end) if speed[i] is not None]
            apex = min(window)[1]
            found.append(Zone(len(found) + 1, step, apex, min(apex + WINDOW, STEPS)))
            step = apex + WINDOW
        else:
            step += 1
    return found


def _brake_start(trace: Trace, zone: Zone) -> int | None:
    """The last speed peak of the lap before the apex of the zone."""
    low = max(1, zone.start - WINDOW * 2)
    best = None
    for i in range(low, zone.apex):
        here, before = trace.speed[i], trace.speed[i - 1]
        if here is None or before is None:
            continue
        ahead = [v for v in trace.speed[i : i + WINDOW] if v is not None]
        if here >= before and ahead and here - min(ahead) >= MIN_DROP_KMH / 2:
            best = i
            break
    return best


def _apex_speed(trace: Trace, zone: Zone) -> float | None:
    window = [
        trace.speed[i]
        for i in range(max(0, zone.apex - WINDOW), min(STEPS, zone.apex + WINDOW))
        if trace.speed[i] is not None
    ]
    return min(window) if window else None


@dataclass
class Advice:
    kind: str  # "brake_later", "carry_speed", or "consistent_exit"
    zone: int
    position: float  # 0 to 1 around the lap.
    reference_value: float
    lap_values: list[float]  # One value for each lap of the driver, in lap order.
    difference: float  # Meters for braking, km/h for speeds.
    laps_showing: int
    laps_total: int


@dataclass
class Analysis:
    zones: int
    advice: list[Advice] = field(default_factory=list)


def analyze(reference: Trace, laps: list[Trace], length_m: float | None) -> Analysis:
    found = zones(reference)
    result = Analysis(zones=len(found))
    if len(laps) < MIN_LAPS:
        return result
    meters_per_step = (length_m or 0) / STEPS
    for zone in found:
        position = round(zone.start / STEPS, 3)
        if meters_per_step:
            starts = [_brake_start(lap, zone) for lap in laps]
            early = [(zone.start - s) * meters_per_step for s in starts if s is not None]
            showing = sum(1 for m in early if m >= EARLY_M)
            if len(early) >= MIN_LAPS and showing >= max(MIN_LAPS, REPEAT_SHARE * len(early)):
                result.advice.append(
                    Advice(
                        "brake_later",
                        zone.number,
                        position,
                        0.0,
                        [round(m) for m in early],
                        round(mean(early)),
                        showing,
                        len(early),
                    )
                )
        reference_apex = _apex_speed(reference, zone)
        apexes = [v for v in (_apex_speed(lap, zone) for lap in laps) if v is not None]
        if reference_apex is not None and len(apexes) >= MIN_LAPS:
            slower = sum(1 for v in apexes if reference_apex - v >= SLOW_KMH)
            if slower >= max(MIN_LAPS, REPEAT_SHARE * len(apexes)):
                result.advice.append(
                    Advice(
                        "carry_speed",
                        zone.number,
                        round(zone.apex / STEPS, 3),
                        round(reference_apex, 1),
                        [round(v, 1) for v in apexes],
                        round(reference_apex - mean(apexes), 1),
                        slower,
                        len(apexes),
                    )
                )
        exits = [lap.speed[zone.exit] for lap in laps if lap.speed[zone.exit] is not None]
        reference_exit = reference.speed[zone.exit]
        if reference_exit is not None and len(exits) >= 3 and pstdev(exits) >= SPREAD_KMH:
            result.advice.append(
                Advice(
                    "consistent_exit",
                    zone.number,
                    round(zone.exit / STEPS, 3),
                    round(reference_exit, 1),
                    [round(v, 1) for v in exits],
                    round(pstdev(exits), 1),
                    len(exits),
                    len(exits),
                )
            )
    return result
