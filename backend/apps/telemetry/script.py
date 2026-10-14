"""Laps from the Paddock script, and the server sessions that they belong to.

The league server sends the Paddock script into AC when a driver joins (phase 2 of
docs/plans/ac-integration.md). The script sends each lap with the race code of the
championship and the Steam ID of the driver. Every driver on the server gets the race code, so
the Steam ID alone proves nothing. The server collector is the witness: a lap counts only when
the server recorded the same lap for this Steam ID, with the same lap time, in a session on the
same track and with the same car. Only the first upload of a server lap counts. A lap that
fails a check goes nowhere.

The server sessions come from the collector events on the fly, as for the incidents and the
replay. The order does not matter: a lap that comes before the server data waits, and the app
matches it again when the events come.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.collectors.incident_api import AC_SESSION_TYPES
from apps.collectors.models import CollectorEvent
from apps.competition.models import Championship, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.imports.ac_results import track_key

from .models import ScriptCode, TelemetryLap
from .services import TelemetryError

# An old race code still works for this long after a new one, for a race in progress.
CODE_GRACE = timedelta(hours=6)
# A lap waits this long for the server data. After that it goes nowhere.
PENDING_LIMIT = timedelta(hours=12)
# The clocks of the server PC and of the app can differ by a little.
TOLERANCE = timedelta(minutes=2)
# The server events that the app reads around a lap.
WINDOW = timedelta(hours=12)
ROUND_WINDOW = timedelta(hours=12)
SAMPLE_HZ = 20
# A long lap is normal: the lap timer runs through a crash and a pit stop until the car
# crosses the line. 36,000 samples at 20 each second is a lap of 30 minutes.
MAX_SCRIPT_SAMPLES = 36_000
TIMELINE_KINDS = ("session_started", "session_ended", "connected", "disconnected", "lap_completed")
# The lap time of the script and of the server for the same lap.
LAP_TIME_TOLERANCE_MS = 50


# Race codes


def current_code(championship: Championship, user=None) -> ScriptCode:
    """The race code of the championship. The first call makes one."""
    code = championship.script_codes.filter(replaced_at__isnull=True).first()
    return code or ScriptCode.objects.create(
        championship=championship, code=secrets.token_urlsafe(18), created_by=user
    )


def new_code(championship: Championship, user) -> ScriptCode:
    """Replace the race code. The old code still works for CODE_GRACE."""
    with transaction.atomic():
        championship.script_codes.filter(replaced_at__isnull=True).update(
            replaced_at=timezone.now()
        )
        return ScriptCode.objects.create(
            championship=championship, code=secrets.token_urlsafe(18), created_by=user
        )


def championship_for_code(raw: str) -> Championship | None:
    if not raw:
        return None
    code = ScriptCode.objects.select_related("championship__league").filter(code=raw).first()
    if code is None:
        return None
    if code.replaced_at and code.replaced_at < timezone.now() - CODE_GRACE:
        return None
    return code.championship


# The server timeline


@dataclass
class Span:
    """One session of one collector run, from its start to the next start or its end."""

    token_id: int
    run_id: str
    started_at: datetime
    ended_at: datetime | None  # None while the session runs.
    session_type: str
    track: str
    layout: str


@dataclass
class Presence:
    """One connection of one driver to the server."""

    token_id: int
    run_id: str
    guid: str
    car_model: str
    started_at: datetime
    ended_at: datetime | None  # None while the driver is connected.


@dataclass
class ServerLap:
    """One lap that the server recorded."""

    token_id: int
    run_id: str
    guid: str
    lap_ms: int
    cuts: int
    at: datetime


@dataclass
class Timeline:
    spans: list[Span]
    presences: list[Presence]
    laps: list[ServerLap]
    latest_event_at: datetime | None


def timeline(championship: Championship, around: datetime) -> Timeline:
    events = CollectorEvent.objects.filter(
        token__championship=championship,
        kind__in=TIMELINE_KINDS,
        occurred_at__gte=around - WINDOW,
        occurred_at__lte=around + WINDOW,
    ).order_by("token_id", "run_id", "seq")
    spans: list[Span] = []
    presences: list[Presence] = []
    laps: list[ServerLap] = []
    open_spans: dict[tuple[int, str], Span] = {}
    open_presences: dict[tuple[int, str, str], Presence] = {}
    # Any event, also a lap or a position, shows how far the server data goes.
    latest = (
        CollectorEvent.objects.filter(
            token__championship=championship,
            occurred_at__gte=around - WINDOW,
            occurred_at__lte=around + WINDOW,
        )
        .aggregate(latest=Max("occurred_at"))
        .get("latest")
    )
    for event in events:
        run = (event.token_id, event.run_id)
        data = event.data or {}
        if event.kind in ("session_started", "session_ended"):
            previous = open_spans.pop(run, None)
            if previous:
                previous.ended_at = event.occurred_at
        if event.kind == "session_started":
            span = Span(
                token_id=event.token_id,
                run_id=event.run_id,
                started_at=event.occurred_at,
                ended_at=None,
                session_type=AC_SESSION_TYPES.get(data.get("type"), ""),
                track=track_key(str(data.get("track", ""))),
                layout=str(data.get("layout", "")),
            )
            spans.append(span)
            open_spans[run] = span
        elif event.kind == "connected":
            presence = Presence(
                token_id=event.token_id,
                run_id=event.run_id,
                guid=str(data.get("guid", "")),
                car_model=str(data.get("car_model", "")),
                started_at=event.occurred_at,
                ended_at=None,
            )
            presences.append(presence)
            open_presences[(*run, presence.guid)] = presence
        elif event.kind == "lap_completed" and data.get("guid"):
            laps.append(
                ServerLap(
                    token_id=event.token_id,
                    run_id=event.run_id,
                    guid=str(data["guid"]),
                    lap_ms=int(data.get("lap_ms") or 0),
                    cuts=int(data.get("cuts") or 0),
                    at=event.occurred_at,
                )
            )
        elif event.kind == "disconnected":
            presence = open_presences.pop((*run, str(data.get("guid", ""))), None)
            if presence:
                presence.ended_at = event.occurred_at
    return Timeline(spans, presences, laps, latest)


def _inside(start: datetime, end: datetime | None, moment: datetime) -> bool:
    return start - TOLERANCE <= moment and (end is None or moment <= end + TOLERANCE)


def _find_round(championship: Championship, track: str, when: datetime) -> Round | None:
    rounds = list(
        Round.objects.filter(
            season__championship=championship,
            track_layout__track__key=track,
            scheduled_at__gte=when - ROUND_WINDOW,
            scheduled_at__lte=when + ROUND_WINDOW,
            cancelled_at__isnull=True,
        )
    )
    return rounds[0] if len(rounds) == 1 else None


def _attempt_number(line: Timeline, span: Span, round_: Round | None) -> int | None:
    """The race start number of a race span: the race spans of the round night up to this one."""
    if span.session_type != "race" or round_ is None or round_.scheduled_at is None:
        return None
    starts = [
        s.started_at
        for s in line.spans
        if s.session_type == "race"
        and s.track == span.track
        and abs(s.started_at - round_.scheduled_at) <= ROUND_WINDOW
        and s.started_at <= span.started_at
    ]
    return len(starts) or None


# Laps


def match(lap: TelemetryLap) -> str:
    """Link a pending lap to its session. Gives "league", "pending", or "rejected". A rejected
    lap is deleted."""
    line = timeline(lap.championship, lap.recorded_at)
    guid = lap.driver.steam_guid or ""
    for span in line.spans:
        if not _inside(span.started_at, span.ended_at, lap.recorded_at):
            continue
        connected = [
            p
            for p in line.presences
            if (p.token_id, p.run_id) == (span.token_id, span.run_id)
            and p.guid == guid
            and _inside(p.started_at, p.ended_at, lap.recorded_at)
        ]
        same_car = [p for p in connected if p.car_model.lower() == lap.car.lower()]
        if span.track != lap.track or not same_car:
            continue
        witnessed = [
            server_lap
            for server_lap in line.laps
            if (server_lap.token_id, server_lap.run_id) == (span.token_id, span.run_id)
            and server_lap.guid == guid
            and abs(server_lap.lap_ms - lap.lap_time_ms) <= LAP_TIME_TOLERANCE_MS
            and abs(server_lap.at - lap.recorded_at) <= TOLERANCE
        ]
        if not witnessed:
            continue
        already = (
            TelemetryLap.objects.filter(
                driver=lap.driver,
                match=TelemetryLap.Match.LEAGUE,
                server_session_at=span.started_at,
                lap_time_ms__gte=lap.lap_time_ms - LAP_TIME_TOLERANCE_MS,
                lap_time_ms__lte=lap.lap_time_ms + LAP_TIME_TOLERANCE_MS,
            )
            .exclude(pk=lap.pk)
            .exists()
        )
        if already:
            break  # A second upload of the same server lap goes nowhere.
        # The server is the truth for the lap number and the cuts. The values that CSP gives
        # to the script can be wrong, for example after a lap with a track cut.
        server_lap = witnessed[0]
        session_laps = [
            other
            for other in line.laps
            if (other.token_id, other.run_id, other.guid)
            == (server_lap.token_id, server_lap.run_id, guid)
            and span.started_at <= other.at <= server_lap.at
        ]
        lap.lap_number = len(session_laps)
        lap.valid = server_lap.cuts == 0
        lap.cuts = server_lap.cuts
        round_ = _find_round(lap.championship, span.track, span.started_at)
        lap.round = round_
        lap.session_type = span.session_type
        lap.server_session_at = span.started_at
        lap.attempt_number = _attempt_number(line, span, round_)
        lap.match = TelemetryLap.Match.LEAGUE
        lap.save(
            update_fields=[
                "lap_number",
                "valid",
                "cuts",
                "round",
                "session_type",
                "server_session_at",
                "attempt_number",
                "match",
            ]
        )
        return "league"
    waiting = line.latest_event_at is None or line.latest_event_at < lap.recorded_at + TOLERANCE
    if waiting and lap.recorded_at > timezone.now() - PENDING_LIMIT:
        return "pending"
    lap.samples.delete(save=False)
    lap.delete()
    return "rejected"


def rematch(championship: Championship) -> int:
    """Match again the waiting laps of a championship, for example after new server events.
    Gives the count of laps that now count."""
    count = 0
    for lap in TelemetryLap.objects.filter(
        championship=championship, match=TelemetryLap.Match.PENDING
    ).select_related("driver", "championship"):
        if match(lap) == "league":
            count += 1
    return count


def _channels(samples: list) -> dict[str, list]:
    """The script sends one row for each sample: time, position, speed, gas, brake, steer,
    gear, rpm. The app stores one list for each channel, as for the driver collector."""
    names = ["t_ms", "pos", "speed_kmh", "gas", "brake", "steer", "gear", "rpm"]
    if not 0 < len(samples) <= MAX_SCRIPT_SAMPLES:
        raise TelemetryError("bad_samples")
    channels: dict[str, list] = {name: [] for name in names}
    for row in samples:
        if not isinstance(row, list) or len(row) != len(names):
            raise TelemetryError("bad_samples")
        for name, value in zip(names, row, strict=True):
            if not isinstance(value, int | float):
                raise TelemetryError("bad_samples")
            channels[name].append(value)
    return channels


def receive_lap(championship: Championship, payload: dict) -> tuple[TelemetryLap | None, str]:
    """Store one lap of the script and match it. Gives the lap (None when rejected) and the
    state: "league", "pending", "rejected", or "known" for a lap that came before."""
    guid = str(payload.get("steam_id", ""))
    driver = DriverProfile.objects.filter(steam_guid=guid).first() if guid else None
    if driver is None:
        raise TelemetryError("unknown_driver")
    if not SeasonEntry.objects.filter(season__championship=championship, driver=driver).exists():
        raise TelemetryError("not_in_championship")
    channels = _channels(payload.get("samples") or [])
    # The PC clock of the driver can be wrong. The age of the lap at the upload is right.
    age = max(0, int(payload["sent_at"]) - int(payload["ended_at"]))
    recorded_at = timezone.now() - timedelta(seconds=age)
    content = json.dumps(channels, separators=(",", ":"), sort_keys=True).encode()
    sha256 = hashlib.sha256(
        content + f"{payload['ended_at']}:{payload['lap_number']}".encode()
    ).hexdigest()
    existing = TelemetryLap.objects.filter(driver=driver, sha256=sha256).first()
    if existing:
        return existing, "known"
    lap = TelemetryLap(
        driver=driver,
        source=TelemetryLap.Source.SCRIPT,
        championship=championship,
        match=TelemetryLap.Match.PENDING,
        sha256=sha256,
        track=track_key(str(payload.get("track", "")))[:100],
        car=str(payload.get("car", ""))[:100],
        lap_number=int(payload["lap_number"]),
        lap_time_ms=int(payload["lap_time_ms"]),
        valid=bool(payload.get("valid", True)),
        recorded_at=recorded_at,
        sample_hz=SAMPLE_HZ,
        uploaded_by=driver.user,
    )
    lap.samples.save("samples.json", ContentFile(content), save=False)
    with transaction.atomic():
        lap.save()
    state = match(lap)
    return (None if state == "rejected" else lap), state


@dataclass
class Now:
    session_type: str
    track: str
    round_number: int | None


def now(championship: Championship) -> Now | None:
    """The league session that runs now, for the line in AC."""
    moment = timezone.now()
    line = timeline(championship, moment)
    running = [s for s in line.spans if s.ended_at is None and s.started_at <= moment + TOLERANCE]
    if not running:
        return None
    span = max(running, key=lambda s: s.started_at)
    round_ = _find_round(championship, span.track, span.started_at)
    return Now(span.session_type, span.track, round_.number if round_ else None)
