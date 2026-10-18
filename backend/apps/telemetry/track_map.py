"""The map of a track from the positions that the server collector records.

Each position sample of the collector has the world x and z and the place on the lap (the
spline position, 0 to 1). The map is the fastest full lap of any car: a lap through the pit lane
is slower, so the pit lane does not go into the drawing. A telemetry sample has only the place on
the lap, so the map gives it its point on the track.
"""

from datetime import timedelta

from apps.collectors.models import CollectorEvent
from apps.competition.models import Round

WINDOW = timedelta(hours=12)
# A full lap has a sample at least each 2 % of the lap.
MAX_HOLE = 0.02


def _laps(stream: list[tuple[int, float, float, float]]):
    """Split the samples of one car into laps at the finish line."""
    lap: list[tuple[int, float, float, float]] = []
    for sample in stream:
        if lap and lap[-1][3] > 0.9 and sample[3] < 0.1:
            yield lap
            lap = []
        lap.append(sample)
    if lap:
        yield lap


def _full(lap: list[tuple[int, float, float, float]]) -> bool:
    splines = sorted(s[3] for s in lap)
    if not splines or splines[0] > MAX_HOLE or splines[-1] < 1 - MAX_HOLE:
        return False
    return all(b - a <= MAX_HOLE for a, b in zip(splines, splines[1:], strict=False))


def track_map(round_: Round) -> list[tuple[float, float, float]]:
    """The (spline, x, z) points of the track, in lap order. Empty without a full lap."""
    if round_.scheduled_at is None:
        return []
    events = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
        kind="positions",
    ).order_by("occurred_at", "token_id", "run_id", "seq")
    streams: dict[str, list[tuple[int, float, float, float]]] = {}
    for event in events.iterator():
        base = int(event.occurred_at.timestamp() * 1000)
        for car, samples in (event.data or {}).get("cars", {}).items():
            for sample in samples:
                if len(sample) >= 4:
                    offset, x, z, spline = sample[:4]
                    streams.setdefault(car, []).append(
                        (base + int(offset), float(x), float(z), float(spline))
                    )
    best: list[tuple[int, float, float, float]] | None = None
    best_ms = None
    for stream in streams.values():
        for lap in _laps(stream):
            if not _full(lap):
                continue
            duration = lap[-1][0] - lap[0][0]
            if best_ms is None or duration < best_ms:
                best, best_ms = lap, duration
    if best is None:
        return []
    ordered = sorted(best, key=lambda s: s[3])
    return [(round(s[3], 5), round(s[1], 2), round(s[2], 2)) for s in ordered]
