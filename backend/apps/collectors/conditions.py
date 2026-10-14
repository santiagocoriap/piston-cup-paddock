"""The real conditions of a round, from the server collector, and the check against the
announced conditions (phase 3 of docs/plans/ac-integration.md).

At each new session, the collector sends the weather and the temperatures from the server, and
the time of day and the start grip from server_cfg.ini when the owner gives its path.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.competition.models import Round
from apps.imports.ac_results import track_key

from .incident_api import AC_SESSION_TYPES
from .models import CollectorEvent

WINDOW = timedelta(hours=12)
# The order of preference: the race shows the conditions of the round best.
PREFERENCE = ("race", "qualifying", "practice")
# How far the real value can be from the announced one before the app warns.
AIR_TOLERANCE_C = 2
TRACK_TOLERANCE_C = 3
TIME_TOLERANCE_MIN = 30
GRIP_TOLERANCE_PCT = 3


@dataclass
class ServerConditions:
    session_type: str
    started_at: datetime
    weather: str | None
    air_temp_c: int | None
    track_temp_c: int | None
    time_of_day: str | None
    grip_pct: int | None


def server_conditions(round_: Round) -> ServerConditions | None:
    """The conditions of the last session of the round night on the server: the race when there
    is one. None when the collector sent nothing for the round."""
    if round_.scheduled_at is None:
        return None
    events = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        kind="session_started",
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
    ).order_by("occurred_at", "seq")
    track = round_.track_layout.track.key
    found: dict[str, CollectorEvent] = {}
    for event in events:
        data = event.data or {}
        if track_key(str(data.get("track", ""))) != track:
            continue
        found[AC_SESSION_TYPES.get(data.get("type"), "")] = event  # The last one wins.
    for kind in PREFERENCE:
        event = found.get(kind)
        if event is None:
            continue
        data = event.data or {}
        return ServerConditions(
            session_type=kind,
            started_at=event.occurred_at,
            weather=data.get("weather"),
            air_temp_c=data.get("air_temp_c"),
            track_temp_c=data.get("road_temp_c"),
            time_of_day=data.get("time_of_day"),
            grip_pct=data.get("grip_pct"),
        )
    return None


def _minutes(value: str | None) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    return int(match[1]) * 60 + int(match[2]) if match else None


def _percent(value) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match[0]) if match else None


def differences(announced: dict, real: ServerConditions | None) -> list[str]:
    """The conditions that the server did not use as announced, as codes."""
    if real is None or not announced:
        return []
    found = []
    air = announced.get("air_temp_c")
    if (
        air is not None
        and real.air_temp_c is not None
        and abs(air - real.air_temp_c) > AIR_TOLERANCE_C
    ):
        found.append("air_temp")
    road = announced.get("track_temp_c")
    if (
        road is not None
        and real.track_temp_c is not None
        and abs(road - real.track_temp_c) > TRACK_TOLERANCE_C
    ):
        found.append("track_temp")
    planned, used = _minutes(announced.get("time_of_day")), _minutes(real.time_of_day)
    if planned is not None and used is not None and abs(planned - used) > TIME_TOLERANCE_MIN:
        found.append("time_of_day")
    grip = _percent(announced.get("grip"))
    if (
        grip is not None
        and real.grip_pct is not None
        and abs(grip - real.grip_pct) > GRIP_TOLERANCE_PCT
    ):
        found.append("grip")
    return found
