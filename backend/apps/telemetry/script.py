"""Laps from the Paddock script, and the server sessions that they belong to.

The league server sends the Paddock script into AC when a driver joins (phase 2 of
docs/plans/ac-integration.md). The script sends each lap with the race code of the
championship and the Steam ID of the driver. Every driver on the server gets the race code, so
the Steam ID alone proves nothing. The server collector is the witness: a lap counts only when
the server recorded the same lap for this Steam ID, with the same lap time, in a session on the
same track and with the same car. Only the first upload of a server lap counts. The app keeps
a lap that fails a check, with the reason ("flagged"). An admin reviews it: check it again, for
example after a new Steam ID of the driver, count it, or delete it.

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
from django.db.models import DurationField, ExpressionWrapper, F, Max, Min, Sum
from django.utils import timezone

from apps.collectors.incident_api import AC_SESSION_TYPES
from apps.collectors.models import CollectorEvent
from apps.competition.models import Championship, Round, SeasonEntry
from apps.identity.models import DriverProfile, driver_for_guid
from apps.imports.ac_results import track_key

from .models import ScriptCode, TelemetryLap
from .samples import covers_lap, pack_samples, trim_to_lap
from .services import TelemetryError

# An old race code still works for this long after a new one, for a race in progress.
CODE_GRACE = timedelta(hours=6)
# A lap waits this long for the server data. After that an admin reviews it.
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
# A server lap with the same lap time counts up to this far from the lap of the script. The lap
# time is the strong check: this window only keeps a lap of an hour before from counting.
MATCH_WINDOW = timedelta(minutes=10)
# Every driver on the server has the race code. This limit stops a flood of laps that do not
# count. One lap of 100 seconds takes about 80 KB, so 1 GB is about 12,000 laps.
MAX_REVIEW_BYTES = 1024**3
# The checks of a lap in order. A failed lap gets the last check that it reached.
MATCH_ISSUES = ("no_session", "other_track", "not_connected", "other_car", "no_server_lap")
# A new check does not repair the samples, and a lap with these issues cannot count.
SAMPLE_ISSUES = ("bad_samples", "partial_samples")


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


def clock_shifts(championship: Championship, around: datetime) -> dict[tuple[int, str], timedelta]:
    """The time to add to the events of each collector run, to get the time of the app.

    The collector PC writes the time of each event with its own clock. The app receives each
    event after it happens, so an event with a time after its arrival shows a PC clock that runs
    ahead. The shift is the largest of these differences. A clock that runs behind is not
    visible this way (the upload can wait), and MATCH_WINDOW covers it."""
    rows = (
        CollectorEvent.objects.filter(
            token__championship=championship,
            occurred_at__gte=around - WINDOW,
            occurred_at__lte=around + WINDOW,
        )
        .values("token_id", "run_id")
        .annotate(
            delay=Min(
                ExpressionWrapper(F("received_at") - F("occurred_at"), output_field=DurationField())
            )
        )
    )
    return {(r["token_id"], r["run_id"]): min(r["delay"], timedelta(0)) for r in rows}


def timeline(championship: Championship, around: datetime) -> Timeline:
    """The sessions, connections, and laps around a moment, all in the time of the app."""
    events = CollectorEvent.objects.filter(
        token__championship=championship,
        kind__in=TIMELINE_KINDS,
        occurred_at__gte=around - WINDOW,
        occurred_at__lte=around + WINDOW,
    ).order_by("token_id", "run_id", "seq")
    shifts = clock_shifts(championship, around)
    spans: list[Span] = []
    presences: list[Presence] = []
    laps: list[ServerLap] = []
    open_spans: dict[tuple[int, str], Span] = {}
    open_presences: dict[tuple[int, str, str], Presence] = {}
    # Any event, also a lap or a position, shows how far the server data goes.
    ends = (
        CollectorEvent.objects.filter(
            token__championship=championship,
            occurred_at__gte=around - WINDOW,
            occurred_at__lte=around + WINDOW,
        )
        .values("token_id", "run_id")
        .annotate(last=Max("occurred_at"))
    )
    latest = max(
        (r["last"] + shifts.get((r["token_id"], r["run_id"]), timedelta(0)) for r in ends),
        default=None,
    )
    for event in events:
        run = (event.token_id, event.run_id)
        data = event.data or {}
        event.occurred_at += shifts.get(run, timedelta(0))
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


def _flag(lap: TelemetryLap, issues: list[str], hint: dict | None = None) -> str:
    lap.match = TelemetryLap.Match.FLAGGED
    lap.issues = issues
    fields = ["match", "issues"]
    if hint is not None:
        lap.summary = {**lap.summary, "match_hint": hint}
        fields.append("summary")
    lap.save(update_fields=fields)
    return "rejected"


def _nearest(line: Timeline, guids: set[str], lap: TelemetryLap) -> dict | None:
    """The server lap of the driver nearest to this lap, for the admin: the time between them in
    seconds, and the difference of the lap times in ms. First the laps with the same lap time."""
    mine = [s for s in line.laps if s.guid in guids]
    if not mine:
        return {"server_laps": 0}
    found = min(
        mine,
        key=lambda s: (
            abs(s.lap_ms - lap.lap_time_ms) > LAP_TIME_TOLERANCE_MS,
            abs(s.at - lap.recorded_at),
        ),
    )
    return {
        "server_laps": len(mine),
        "seconds": round((found.at - lap.recorded_at).total_seconds()),
        "lap_ms": found.lap_ms - lap.lap_time_ms,
    }


def match(lap: TelemetryLap, line: Timeline | None = None) -> str:
    """Link a pending lap to its session. Gives "league", "pending", or "rejected". A rejected
    lap stays, flagged with the reason, for an admin. A caller with many laps of one night can
    give the timeline, so the app reads the events one time."""
    line = line or timeline(lap.championship, lap.recorded_at)
    guids = set(lap.driver.guids())
    reached = 0  # The index in MATCH_ISSUES of the check that failed.
    for span in line.spans:
        if not _inside(span.started_at, span.ended_at, lap.recorded_at):
            continue
        if span.track != lap.track:
            reached = max(reached, 1)
            continue
        connected = [
            p
            for p in line.presences
            if (p.token_id, p.run_id) == (span.token_id, span.run_id)
            and p.guid in guids
            and _inside(p.started_at, p.ended_at, lap.recorded_at)
        ]
        same_car = [p for p in connected if p.car_model.lower() == lap.car.lower()]
        if not connected:
            reached = max(reached, 2)
            continue
        if not same_car:
            reached = max(reached, 3)
            continue
        witnessed = [
            server_lap
            for server_lap in line.laps
            if (server_lap.token_id, server_lap.run_id) == (span.token_id, span.run_id)
            and server_lap.guid in guids
            and abs(server_lap.lap_ms - lap.lap_time_ms) <= LAP_TIME_TOLERANCE_MS
            and abs(server_lap.at - lap.recorded_at) <= MATCH_WINDOW
        ]
        witnessed.sort(key=lambda s: abs(s.at - lap.recorded_at))
        if not witnessed:
            reached = max(reached, 4)
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
            return _flag(lap, ["duplicate"])  # A second upload of the same server lap.
        # The server is the truth for the lap number and the cuts. The values that CSP gives
        # to the script can be wrong, for example after a lap with a track cut.
        server_lap = witnessed[0]
        session_laps = [
            other
            for other in line.laps
            if (other.token_id, other.run_id, other.guid)
            == (server_lap.token_id, server_lap.run_id, server_lap.guid)
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
    hint = _nearest(line, guids, lap) if MATCH_ISSUES[reached] == "no_server_lap" else None
    return _flag(lap, [MATCH_ISSUES[reached]], hint)


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


# The channels of each sample. An older script sends only the first 8.
CORE_CHANNELS = ["t_ms", "pos", "speed_kmh", "gas", "brake", "steer", "gear", "rpm"]
MOTION_CHANNELS = ["x", "z", "g_lat", "g_long"]
WHEELS = ("fl", "fr", "rl", "rr")
# The channels of the second block, at 5 samples each second. The order is the order of paddock.lua.
VEHICLE_CHANNELS = [
    "t_ms",
    "pos",
    "in_pit",
    "fuel",
    *[f"{kind}_{w}" for kind in ("temp_core", "temp_in", "temp_mid", "temp_out") for w in WHEELS],
    *[f"{kind}_{w}" for kind in ("pressure", "wear", "slip", "susp") for w in WHEELS],
]
MAX_VEHICLE_SAMPLES = 9_000


def _rows(samples: list, names: list[str]) -> dict[str, list]:
    channels: dict[str, list] = {name: [] for name in names}
    for row in samples:
        if not isinstance(row, list) or len(row) != len(names):
            raise TelemetryError("bad_samples")
        for name, value in zip(names, row, strict=True):
            if not isinstance(value, int | float):
                raise TelemetryError("bad_samples")
            channels[name].append(value)
    return channels


def _channels(samples: list) -> dict[str, list]:
    """The script sends one row for each sample. The app stores one list for each channel."""
    if not 0 < len(samples) <= MAX_SCRIPT_SAMPLES:
        raise TelemetryError("bad_samples")
    full = [*CORE_CHANNELS, *MOTION_CHANNELS]
    return _rows(samples, CORE_CHANNELS if len(samples[0]) == len(CORE_CHANNELS) else full)


def _vehicle(samples: list, lap_time_ms: int) -> tuple[dict[str, list], dict]:
    """The second block, with the prefix "v_", and the numbers of the lap from it. A bad block
    does not stop the lap: the app keeps the lap without these channels."""
    if not samples or len(samples) > MAX_VEHICLE_SAMPLES:
        return {}, {}
    try:
        rows = trim_to_lap(_rows(samples, VEHICLE_CHANNELS), lap_time_ms)
    except TelemetryError:
        return {}, {}
    if not rows["t_ms"]:
        return {}, {}
    fuel = rows["fuel"]
    in_pit = [t for t, pit in zip(rows["t_ms"], rows["in_pit"], strict=True) if pit]
    wear = [sum(rows[f"wear_{w}"][-1] for w in WHEELS) / len(WHEELS)]
    summary = {
        "fuel_start": fuel[0],
        "fuel_end": fuel[-1],
        "fuel_used": round(fuel[0] - fuel[-1], 3),
        "pit_ms": (in_pit[-1] - in_pit[0]) if in_pit else 0,
        "wear": round(wear[0], 4),
    }
    return {f"v_{name}": values for name, values in rows.items()}, summary


def receive_lap(championship: Championship, payload: dict) -> tuple[TelemetryLap | None, str]:
    """Store one lap of the script and match it. Gives the lap (None when rejected) and the
    state: "league", "pending", "rejected", or "known" for a lap that came before."""
    guid = str(payload.get("steam_id", ""))[:17]
    driver = driver_for_guid(guid)
    issues = _driver_issues(championship, driver)
    try:
        channels = trim_to_lap(_channels(payload.get("samples") or []), int(payload["lap_time_ms"]))
        if len(channels["t_ms"]) < 2:
            raise TelemetryError("bad_samples")
    except TelemetryError:
        # The app keeps the samples as they came, for the admin.
        issues.append("bad_samples")
        channels = {"raw": (payload.get("samples") or [])[:MAX_SCRIPT_SAMPLES]}
    else:
        if not covers_lap(channels, int(payload["lap_time_ms"])):
            issues.append("partial_samples")
    extra, summary = _vehicle(payload.get("vehicle") or [], int(payload["lap_time_ms"]))
    channels.update(extra)
    if issues and _review_is_full(championship):
        raise TelemetryError("too_many_flagged")
    # The PC clock of the driver can be wrong. The age of the lap at the upload is right.
    age = max(0, int(payload["sent_at"]) - int(payload["ended_at"]))
    recorded_at = timezone.now() - timedelta(seconds=age)
    content = json.dumps(channels, separators=(",", ":"), sort_keys=True).encode()
    packed = pack_samples(channels)
    sha256 = hashlib.sha256(
        content + f"{payload['ended_at']}:{payload['lap_number']}".encode()
    ).hexdigest()
    existing = TelemetryLap.objects.filter(driver=None, steam_guid=guid, sha256=sha256)
    if driver is not None:
        existing = TelemetryLap.objects.filter(driver=driver, sha256=sha256)
    if found := existing.first():
        return found, "rejected" if found.match == TelemetryLap.Match.FLAGGED else "known"
    lap = TelemetryLap(
        driver=driver,
        steam_guid=guid,
        issues=issues,
        source=TelemetryLap.Source.SCRIPT,
        championship=championship,
        match=TelemetryLap.Match.FLAGGED if issues else TelemetryLap.Match.PENDING,
        sha256=sha256,
        track=track_key(str(payload.get("track", "")))[:100],
        car=str(payload.get("car", ""))[:100],
        lap_number=int(payload["lap_number"]),
        lap_time_ms=int(payload["lap_time_ms"]),
        valid=bool(payload.get("valid", True)),
        recorded_at=recorded_at,
        sample_hz=SAMPLE_HZ,
        samples_bytes=len(packed),
        summary=summary,
        uploaded_by=driver.user if driver else None,
    )
    lap.samples.save("samples.json", ContentFile(packed), save=False)
    with transaction.atomic():
        lap.save()
    if issues:
        return lap, "rejected"
    state = match(lap)
    if state != "league" and _review_is_full(championship):
        lap.samples.delete(save=False)
        lap.delete()
        raise TelemetryError("too_many_flagged")
    return lap, state


def _review_is_full(championship: Championship) -> bool:
    used = TelemetryLap.objects.filter(
        championship=championship,
        match__in=[TelemetryLap.Match.PENDING, TelemetryLap.Match.FLAGGED],
    ).aggregate(total=Sum("samples_bytes"))["total"]
    return (used or 0) >= MAX_REVIEW_BYTES


def _driver_issues(championship: Championship, driver: DriverProfile | None) -> list[str]:
    if driver is None:
        return ["unknown_driver"]
    if not SeasonEntry.objects.filter(season__championship=championship, driver=driver).exists():
        return ["not_in_championship"]
    return []


# Review of the flagged laps


def recheck_all(championship: Championship) -> dict[str, int]:
    """Check again every flagged lap of a championship that a new check can change. The laps
    of one night share one timeline."""
    laps = (
        TelemetryLap.objects.filter(championship=championship, match=TelemetryLap.Match.FLAGGED)
        .exclude(issues__contains=["bad_samples"])
        .exclude(issues__contains=["partial_samples"])
        .select_related("driver", "championship")
        .order_by("recorded_at")
    )
    lines: dict[object, Timeline] = {}
    counts = {"league": 0, "pending": 0, "rejected": 0}
    for lap in laps:
        night = lap.recorded_at.date()
        if night not in lines:
            lines[night] = timeline(championship, lap.recorded_at)
        counts[recheck(lap, lines[night])] += 1
    return counts


def recheck(lap: TelemetryLap, line: Timeline | None = None) -> str:
    """Do all the checks again, for example after an admin adds a Steam ID to a driver. Gives
    "league", "pending", or "rejected" (the lap stays flagged)."""
    if lap.driver is None:
        lap.driver = driver_for_guid(lap.steam_guid)
    issues = _driver_issues(lap.championship, lap.driver)
    issues += [issue for issue in lap.issues if issue in SAMPLE_ISSUES]
    lap.uploaded_by = lap.driver.user if lap.driver else None
    lap.save(update_fields=["driver", "uploaded_by"])
    if issues:
        return _flag(lap, issues)
    lap.match = TelemetryLap.Match.PENDING
    lap.issues = []
    lap.save(update_fields=["match", "issues"])
    return match(lap, line)


def recheck_guid(guid: str) -> int:
    """Check again the flagged laps of a Steam ID that now has a driver. Gives the count of laps
    that now count."""
    laps = TelemetryLap.objects.filter(
        match=TelemetryLap.Match.FLAGGED, driver__isnull=True, steam_guid=guid
    ).select_related("championship")
    return sum(1 for lap in laps if recheck(lap) == "league")


def accept(lap: TelemetryLap, round_: Round, session_type: str) -> None:
    """An admin counts a flagged lap for a round, for example when the collector lost the
    server events. The issues stay on the lap as a record. The cuts stay unknown."""
    if lap.driver is None:
        raise TelemetryError("unknown_driver")
    for issue in lap.issues:
        if issue in SAMPLE_ISSUES:
            raise TelemetryError(issue)
    lap.round = round_
    lap.session_type = session_type
    lap.match = TelemetryLap.Match.LEAGUE
    lap.save(update_fields=["round", "session_type", "match"])


def guess_round(lap: TelemetryLap) -> Round | None:
    """The round of a flagged lap, from its track and its time."""
    return _find_round(lap.championship, lap.track, lap.recorded_at)


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
