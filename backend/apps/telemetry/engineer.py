"""Race engineer: where a driver loses time, corner by corner, and why. Pure functions with no
database.

Every lap goes onto one grid of the lap distance (STEPS points from the start line). The
corners come from the speed of the reference lap: a corner is a low point of the speed after a
clear drop. The lap is cut into one part for each corner, from the speed peak before the corner
to the speed peak before the next corner, so the straight after a corner belongs to it: a slow
exit costs time on the straight.

For each part the engineer measures the time, and with the pedals: where the braking starts,
how hard it is, the lowest speed, where the throttle is full again, the distance without any
pedal, the exit speed, and the gear. A cause is a measured difference with the reference that
is larger than a threshold. The engineer says what is different, not that it is wrong: the
driver tries it.
"""

from dataclasses import dataclass, field
from statistics import pstdev

STEPS = 1000

# Corner detection on the reference speed.
APEX_WINDOW = 15  # A low point is the lowest speed within this many steps on each side.
MIN_DROP_KMH = 12  # The speed must drop this much before the low point.
DROP_LOOKBACK = 60  # Steps before the low point where the drop is measured.
MERGE_STEPS = 25  # Two low points closer than this are one corner.

# Pedal levels.
BRAKE_ON = 0.10
FULL_THROTTLE = 0.95
NO_PEDAL = 0.05
COAST_MIN_KMH = 30

# Causes: a difference larger than these counts.
LOSS_S = 0.04  # A corner with a smaller loss gets no cause.
BRAKE_M = 8
MIN_SPEED_KMH = 3
THROTTLE_M = 10
COAST_M = 10
EXIT_KMH = 3
BRAKE_PRESSURE = 15  # Percent points of the brake pedal.
EXIT_AFTER_M = 30  # The exit speed is this far after the full throttle point of the reference.

# Consistency.
MIN_LAPS_CONSISTENCY = 3
SPREAD_S = 0.08


@dataclass
class Lap:
    """One lap on the grid. None where the lap has no sample. Pedals are 0 to 1."""

    key: int
    speed: list[float | None]
    time: list[float | None]  # Seconds from the first sample.
    gas: list[float | None] | None = None
    brake: list[float | None] | None = None
    gear: list[float | None] | None = None

    @property
    def has_pedals(self) -> bool:
        return self.gas is not None and self.brake is not None


def _unwrap(pos: list[float]) -> list[float]:
    """The lap distance always going up. A lap that starts before the line (a car on the grid)
    starts below 0, and each crossing of the line adds one lap."""
    out: list[float] = []
    offset = -1.0 if pos and pos[0] > 0.5 else 0.0
    top = float("-inf")
    for i, p in enumerate(pos):
        if i and pos[i - 1] - p > 0.5:
            offset += 1
        top = max(top, p + offset)
        out.append(top)
    return out


def _grid(pos: list[float], values: list[float], step: bool = False) -> list[float | None]:
    out: list[float | None] = []
    j = 0
    for k in range(STEPS):
        s = k / (STEPS - 1)
        if not pos or s < pos[0] or s > pos[-1]:
            out.append(None)
            continue
        while j < len(pos) - 2 and pos[j + 1] < s:
            j += 1
        p0, p1 = pos[j], pos[min(j + 1, len(pos) - 1)]
        v0, v1 = values[j], values[min(j + 1, len(values) - 1)]
        if step or p1 == p0:
            out.append(v1 if s >= p1 else v0)
        else:
            out.append(v0 + (v1 - v0) * (s - p0) / (p1 - p0))
    return out


def to_lap(key: int, channels: dict[str, list[float]]) -> Lap:
    pos = _unwrap(channels.get("pos", []))
    n = len(pos)

    def channel(name: str, step: bool = False) -> list[float | None] | None:
        values = channels.get(name)
        return _grid(pos, values, step) if values and len(values) == n else None

    speed = channel("speed_kmh") or [None] * STEPS
    time = _from_line(channel("t_ms") or [None] * STEPS)
    return Lap(key, speed, time, channel("gas"), channel("brake"), channel("gear", step=True))


def _from_line(raw: list[float | None]) -> list[float | None]:
    """Seconds from the start line. The first and the last grid points often have no sample:
    the time there comes from the slope of the two nearest samples."""
    known = [i for i, t in enumerate(raw) if t is not None]
    if len(known) < 2:
        return [None] * len(raw)
    filled = list(raw)
    a, b = known[0], known[1]
    slope = (raw[b] - raw[a]) / (b - a)  # type: ignore[operator]
    for i in range(a):
        filled[i] = raw[a] - slope * (a - i)  # type: ignore[operator]
    y, z = known[-2], known[-1]
    slope = (raw[z] - raw[y]) / (z - y)  # type: ignore[operator]
    for i in range(z + 1, len(raw)):
        filled[i] = raw[z] + slope * (i - z)  # type: ignore[operator]
    start = filled[0]
    return [None if t is None else (t - start) / 1000 for t in filled]  # type: ignore[operator]


def lap_length_m(lap: Lap) -> float | None:
    """The lap length from the speed and the time, when the track has no length."""
    total = 0.0
    for i in range(1, STEPS):
        v, t0, t1 = lap.speed[i - 1], lap.time[i - 1], lap.time[i]
        if v is not None and t0 is not None and t1 is not None and t1 > t0:
            total += v / 3.6 * (t1 - t0)
    return total or None


def _smooth(values: list[float | None], width: int = 3) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        near = [v for v in values[max(0, i - width) : i + width + 1] if v is not None]
        out.append(sum(near) / len(near) if near and values[i] is not None else None)
    return out


@dataclass
class Corner:
    number: int
    start: int  # The speed peak before the corner.
    apex: int  # The lowest reference speed.
    end: int  # The speed peak before the next corner (or the end of the lap).


def corners(reference: Lap) -> list[Corner]:
    speed = _smooth(reference.speed)
    apexes: list[int] = []
    for i in range(STEPS):
        here = speed[i]
        if here is None:
            continue
        around = [v for v in speed[max(0, i - APEX_WINDOW) : i + APEX_WINDOW + 1] if v is not None]
        before = [v for v in speed[max(0, i - DROP_LOOKBACK) : i] if v is not None]
        if here <= min(around) and before and max(before) - here >= MIN_DROP_KMH:
            if apexes and i - apexes[-1] < MERGE_STEPS:
                if here < (speed[apexes[-1]] or 0):
                    apexes[-1] = i
                continue
            apexes.append(i)
    found: list[Corner] = []
    for number, apex in enumerate(apexes, start=1):
        low = apexes[number - 2] if number > 1 else 0
        window = [(speed[i], i) for i in range(low, apex) if speed[i] is not None]
        start = max(window)[1] if window and number > 1 else 0
        found.append(Corner(number, start, apex, STEPS - 1))
    for corner, after in zip(found, found[1:], strict=False):
        corner.end = after.start
    return found


@dataclass
class Metrics:
    """One lap in one corner. Distances in meters from the start line."""

    time_s: float | None
    brake_m: float | None
    brake_peak: float | None  # Percent.
    min_kmh: float | None
    apex_m: float | None
    throttle_m: float | None
    coast_m: float | None
    exit_kmh: float | None
    gear: int | None


def _first(indexes, test) -> int | None:
    return next((i for i in indexes if test(i)), None)


def measure(lap: Lap, corner: Corner, meters: float, exit_step: int | None) -> Metrics:
    a, b = corner.start, corner.end
    t0, t1 = lap.time[a], lap.time[b]
    time_s = t1 - t0 if t0 is not None and t1 is not None else None
    near = range(max(a, corner.apex - 60), min(b, corner.apex + 60))
    speeds = [(lap.speed[i], i) for i in near if lap.speed[i] is not None]
    if not speeds:
        return Metrics(time_s, None, None, None, None, None, None, None, None)
    min_kmh, apex = min(speeds)
    if lap.has_pedals:
        brake = lap.brake or []
        gas = lap.gas or []
        brake_on = _first(range(a, apex + 1), lambda i: (brake[i] or 0) >= BRAKE_ON)
        peak = max((brake[i] or 0) for i in range(a, apex + 1)) * 100
        full = _first(
            range(apex, b),
            lambda i: all((gas[j] or 0) >= FULL_THROTTLE for j in range(i, min(b, i + 5))),
        )
        coast = sum(
            1
            for i in range(a, b)
            if (gas[i] or 0) < NO_PEDAL
            and (brake[i] or 0) < NO_PEDAL
            and (lap.speed[i] or 0) > COAST_MIN_KMH
        )
    else:
        # Without pedals: the braking starts where the speed starts to fall.
        brake_on = _first(
            range(a, apex),
            lambda i: (
                (lap.speed[i] or 0)
                - min((lap.speed[j] or 0) for j in range(i, min(apex + 1, i + 6)))
                > 3
            ),
        )
        peak, full, coast = None, None, None
    exit_kmh = lap.speed[exit_step] if exit_step is not None else None
    gear = lap.gear[apex] if lap.gear else None
    return Metrics(
        round(time_s, 3) if time_s is not None else None,
        round(brake_on * meters, 1) if brake_on is not None else None,
        round(peak) if peak is not None else None,
        round(min_kmh, 1),
        round(apex * meters, 1),
        round(full * meters, 1) if full is not None else None,
        round(coast * meters, 1) if coast is not None else None,
        round(exit_kmh, 1) if exit_kmh is not None else None,
        int(gear) if gear is not None else None,
    )


@dataclass
class Cause:
    # brake_early, brake_late, brake_soft, min_speed, throttle_late, coasting, exit_speed, gear
    kind: str
    yours: float
    reference: float
    difference: float  # Meters, km/h, percent points, or gears.


def causes(mine: Metrics, ref: Metrics) -> list[Cause]:
    found: list[Cause] = []

    def add(kind, yours, reference):
        found.append(Cause(kind, yours, reference, round(yours - reference, 1)))

    if mine.brake_m is not None and ref.brake_m is not None:
        if mine.brake_m <= ref.brake_m - BRAKE_M:
            add("brake_early", mine.brake_m, ref.brake_m)
        elif (
            mine.brake_m >= ref.brake_m + BRAKE_M
            and mine.min_kmh is not None
            and ref.min_kmh is not None
            and mine.min_kmh < ref.min_kmh - 1
        ):
            add("brake_late", mine.brake_m, ref.brake_m)
    if mine.brake_peak is not None and ref.brake_peak is not None:
        if mine.brake_peak <= ref.brake_peak - BRAKE_PRESSURE:
            add("brake_soft", mine.brake_peak, ref.brake_peak)
    if mine.min_kmh is not None and ref.min_kmh is not None:
        if mine.min_kmh <= ref.min_kmh - MIN_SPEED_KMH:
            add("min_speed", mine.min_kmh, ref.min_kmh)
    if mine.throttle_m is not None and ref.throttle_m is not None:
        if mine.throttle_m >= ref.throttle_m + THROTTLE_M:
            add("throttle_late", mine.throttle_m, ref.throttle_m)
    if mine.coast_m is not None and ref.coast_m is not None:
        if mine.coast_m >= ref.coast_m + COAST_M:
            add("coasting", mine.coast_m, ref.coast_m)
    if mine.exit_kmh is not None and ref.exit_kmh is not None:
        if mine.exit_kmh <= ref.exit_kmh - EXIT_KMH:
            add("exit_speed", mine.exit_kmh, ref.exit_kmh)
    if mine.gear is not None and ref.gear is not None and mine.gear != ref.gear:
        add("gear", mine.gear, ref.gear)
    return found


@dataclass
class CornerResult:
    number: int
    start: float  # 0 to 1 around the lap.
    apex: float
    end: float
    loss_s: float | None  # Positive: the lap is slower than the reference here.
    reference_key: int  # The lap that is the reference in this corner.
    yours: Metrics
    reference: Metrics
    causes: list[Cause] = field(default_factory=list)


@dataclass
class Spread:
    number: int
    time_s: float  # The standard deviation of the corner time over the laps.
    brake_m: float | None
    min_kmh: float | None
    best_s: float
    worst_s: float


@dataclass
class Analysis:
    length_m: float | None
    has_pedals: bool
    corners: list[CornerResult]
    ideal_s: float | None  # The best time of each corner over the driver's laps, added up.
    spread: list[Spread]


def analyze(lap: Lap, reference: Lap | None, own: list[Lap], length_m: float | None) -> Analysis:
    """Compare the lap with the reference lap. Without a reference lap, each corner compares
    with the fastest of the driver's own laps in that corner."""
    base = reference or lap
    length = length_m or lap_length_m(base)
    meters = (length or 0) / (STEPS - 1)
    found = corners(base)
    results: list[CornerResult] = []
    for corner in found:
        ref_lap = reference
        if ref_lap is None:
            timed = [
                (m.time_s, other)
                for other in own
                if (m := measure(other, corner, meters, None)).time_s is not None
            ]
            ref_lap = min(timed, key=lambda item: item[0])[1] if timed else lap
        probe = measure(ref_lap, corner, meters, None)
        exit_step = None
        if probe.throttle_m is not None and meters:
            exit_step = min(corner.end, round((probe.throttle_m + EXIT_AFTER_M) / meters))
        elif meters:
            exit_step = min(corner.end, corner.apex + round(60 / meters))
        mine = measure(lap, corner, meters, exit_step)
        theirs = measure(ref_lap, corner, meters, exit_step)
        loss = (
            round(mine.time_s - theirs.time_s, 3)
            if mine.time_s is not None and theirs.time_s is not None
            else None
        )
        result = CornerResult(
            corner.number,
            round(corner.start / (STEPS - 1), 4),
            round(corner.apex / (STEPS - 1), 4),
            round(corner.end / (STEPS - 1), 4),
            loss,
            ref_lap.key,
            mine,
            theirs,
        )
        if loss is not None and loss >= LOSS_S and ref_lap is not lap:
            result.causes = causes(mine, theirs)
        results.append(result)

    ideal = None
    if own:
        best_parts = []
        for corner in found:
            times = [
                m.time_s for other in own if (m := measure(other, corner, meters, None)).time_s
            ]
            best_parts.append(min(times) if times else None)
        if best_parts and all(t is not None for t in best_parts):
            ideal = round(sum(best_parts), 3)

    spread: list[Spread] = []
    if len(own) >= MIN_LAPS_CONSISTENCY:
        for corner in found:
            rows = [measure(other, corner, meters, None) for other in own]
            times = [m.time_s for m in rows if m.time_s is not None]
            if len(times) < MIN_LAPS_CONSISTENCY or pstdev(times) < SPREAD_S:
                continue
            brakes = [m.brake_m for m in rows if m.brake_m is not None]
            mins = [m.min_kmh for m in rows if m.min_kmh is not None]
            spread.append(
                Spread(
                    corner.number,
                    round(pstdev(times), 3),
                    round(pstdev(brakes), 1) if len(brakes) >= 2 else None,
                    round(pstdev(mins), 1) if len(mins) >= 2 else None,
                    round(min(times), 3),
                    round(max(times), 3),
                )
            )
        spread.sort(key=lambda s: -s.time_s)

    return Analysis(round(length) if length else None, lap.has_pedals, results, ideal, spread)
