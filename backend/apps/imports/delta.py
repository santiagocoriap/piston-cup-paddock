"""The time delta between two laps along the track. Pure functions with no database.

The telemetry gives the time in the lap and the normalized track position (0 at the line,
1 at the next line). The delta compares the two laps at the same position, so it aligns by
distance and not by time. Sign: delta = time of lap B - time of lap A at the same position.
A positive value means that lap B is slower (behind) at that point.
"""

STEPS = 200  # Points along the lap.


def _clean(pos: list[float], t_ms: list[float]) -> list[tuple[float, float]]:
    """Keep the samples that go forward around the lap. The first samples can still show the
    end of the last lap (near 1.0), and the last samples can show the next lap (near 0.0)."""
    points: list[tuple[float, float]] = []
    for p, t in zip(pos, t_ms, strict=False):
        if points and p <= points[-1][0]:
            continue  # A position that does not go forward (the line, a reset, or a spin).
        if not points and p > 0.5:
            continue  # The end of the last lap.
        points.append((p, t))
    return points


def _time_at(points: list[tuple[float, float]], position: float) -> float | None:
    """The lap time at a position, with linear interpolation between two samples."""
    if not points or position < points[0][0] or position > points[-1][0]:
        return None
    low, high = 0, len(points) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if points[middle][0] <= position:
            low = middle
        else:
            high = middle
    (p0, t0), (p1, t1) = points[low], points[high]
    if p1 == p0:
        return t0
    return t0 + (t1 - t0) * (position - p0) / (p1 - p0)


def delta(a: dict[str, list[float]], b: dict[str, list[float]]) -> dict | None:
    """The delta of lap B against lap A. None when a lap has no position data."""
    if not all(k in lap for lap in (a, b) for k in ("pos", "t_ms")):
        return None
    points_a = _clean(a["pos"], a["t_ms"])
    points_b = _clean(b["pos"], b["t_ms"])
    if len(points_a) < 2 or len(points_b) < 2:
        return None
    positions, values = [], []
    for step in range(STEPS + 1):
        position = step / STEPS
        time_a = _time_at(points_a, position)
        time_b = _time_at(points_b, position)
        if time_a is None or time_b is None:
            continue
        positions.append(round(position, 4))
        values.append(round(time_b - time_a))
    if not positions:
        return None
    covered = positions[-1] - positions[0]
    return {"pos": positions, "delta_ms": values, "coverage": round(covered, 3)}


def speed_at(lap: dict[str, list[float]], steps: int = STEPS) -> dict | None:
    """The speed of a lap at fixed positions, for one chart with two laps."""
    if "speed_kmh" not in lap:
        return None
    points = _clean(lap["pos"], lap["speed_kmh"])
    rows = [(s / steps, _time_at(points, s / steps)) for s in range(steps + 1)]
    rows = [(p, round(v, 1)) for p, v in rows if v is not None]
    return {"pos": [p for p, _ in rows], "speed_kmh": [v for _, v in rows]}
