"""Position replay of a race start, from the "positions" events of the server collector.

The replay gives the raw samples. The page shows a gap when a car has no sample for more
than one second. It does not invent movement between far samples.
"""

from datetime import datetime, timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.competition.models import Round
from apps.competition.permissions import can_view

from .incident_api import WINDOW, collisions
from .incidents import group
from .models import CollectorEvent

router = Router(tags=["replay"])

RACE = 3  # The AC session type of a race.


class ReplayAttemptOut(Schema):
    number: int
    started_at: datetime


class CarTrackOut(Schema):
    key: str
    name: str
    t_ms: list[int]
    x: list[float]
    z: list[float]


class MarkerOut(Schema):
    t_ms: int
    kind: str  # "incident" or "restart"
    label: str
    incident_key: int | None = None


class ReplayOut(Schema):
    attempts: list[ReplayAttemptOut]
    attempt: int | None
    has_positions: bool
    duration_ms: int
    cars: list[CarTrackOut]
    markers: list[MarkerOut]


def _ms(delta: timedelta) -> int:
    return round(delta.total_seconds() * 1000)


@router.get("/rounds/{round_id}/replay", response=ReplayOut)
def replay(request, round_id: int, attempt: int | None = None):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    empty = ReplayOut(
        attempts=[], attempt=None, has_positions=False, duration_ms=0, cars=[], markers=[]
    )
    if round_.scheduled_at is None:
        return empty
    events = list(
        CollectorEvent.objects.filter(
            token__championship_id=round_.season.championship_id,
            occurred_at__gte=round_.scheduled_at - WINDOW,
            occurred_at__lte=round_.scheduled_at + WINDOW,
        ).order_by("occurred_at", "token_id", "run_id", "seq")
    )
    starts = [
        e for e in events if e.kind == "session_started" and (e.data or {}).get("type") == RACE
    ]
    if not starts:
        return empty
    number = attempt if attempt and 1 <= attempt <= len(starts) else len(starts)
    start = starts[number - 1]
    # The next session start of any kind ends this race start.
    later = [e for e in events if e.kind == "session_started" and e.occurred_at > start.occurred_at]
    end = later[0].occurred_at if later else None

    names = {
        e.driver.steam_guid: e.driver.display_name
        for e in round_.season.entries.select_related("driver")
        if e.driver.steam_guid
    }
    tracks: dict[str, CarTrackOut] = {}
    for event in events:
        if event.occurred_at < start.occurred_at or (end and event.occurred_at >= end):
            continue
        if event.kind == "connected":
            data = event.data or {}
            names.setdefault(data.get("guid", ""), data.get("name", ""))
        if event.kind != "positions":
            continue
        base = _ms(event.occurred_at - start.occurred_at)
        for key, samples in (event.data or {}).get("cars", {}).items():
            track = tracks.setdefault(key, CarTrackOut(key=key, name=key, t_ms=[], x=[], z=[]))
            for offset, x, z, *_ in samples:
                track.t_ms.append(base + int(offset))
                track.x.append(float(x))
                track.z.append(float(z))
    for track in tracks.values():
        track.name = names.get(track.key) or track.key

    markers = []
    found, collision_names, _ = collisions(round_, "race")
    for incident in group(found):
        first = incident.events[0]
        if first.attempt != number:
            continue
        cars = sorted(collision_names.get(car, car) for car in incident.cars)
        markers.append(
            MarkerOut(
                t_ms=_ms(first.at - start.occurred_at),
                kind="incident",
                label=" + ".join(cars),
                incident_key=incident.key,
            )
        )
    if number < len(starts) and end:
        markers.append(MarkerOut(t_ms=_ms(end - start.occurred_at), kind="restart", label=""))
    duration = max([0, *(t for track in tracks.values() for t in track.t_ms)])
    return ReplayOut(
        attempts=[
            ReplayAttemptOut(number=i + 1, started_at=s.occurred_at) for i, s in enumerate(starts)
        ],
        attempt=number,
        has_positions=bool(tracks),
        duration_ms=max(duration, *(m.t_ms for m in markers)) if markers else duration,
        cars=sorted(tracks.values(), key=lambda c: c.name),
        markers=sorted(markers, key=lambda m: m.t_ms),
    )
