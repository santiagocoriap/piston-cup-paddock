"""Driver telemetry: receive laps from the driver collector, and decide who sees what.

Access levels:
- "full": every channel, with the driver inputs.
- "laps": lap time, track position, and speed. No inputs.
- None: nothing.

The driver always has full access. Other drivers get "laps" at most, whatever the driver
chooses, so they never see inputs or setups. Basic results never need telemetry.
"""

import hashlib
import json
import secrets
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.competition.models import Round, SeasonEntry
from apps.competition.permissions import can_manage, can_view
from apps.identity.models import DriverProfile
from apps.imports.ac_results import track_key

from .models import Access, DriverKey, TelemetryLap, TelemetrySharing

PUBLIC_CHANNELS = ["t_ms", "pos", "speed_kmh"]
PROTECTED_CHANNELS = ["gas", "brake", "steer", "gear", "rpm"]
CHANNELS = PUBLIC_CHANNELS + PROTECTED_CHANNELS
MAX_SAMPLES = 20_000
MATCH_WINDOW = timedelta(hours=12)
RANK = {None: 0, Access.NONE: 0, Access.LAPS: 1, Access.FULL: 2}


class TelemetryError(ValueError):
    pass


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_key(driver: DriverProfile) -> str:
    """Make a new key. The old key of the driver stops working."""
    raw = "pdc_" + secrets.token_urlsafe(32)
    DriverKey.objects.update_or_create(
        driver=driver, defaults={"token_hash": _hash(raw), "last_seen_at": None}
    )
    return raw


def authenticate(raw: str) -> DriverKey | None:
    key = DriverKey.objects.filter(token_hash=_hash(raw)).select_related("driver__user").first()
    if key:
        DriverKey.objects.filter(pk=key.pk).update(last_seen_at=timezone.now())
    return key


def sharing_for(driver: DriverProfile) -> TelemetrySharing:
    sharing, _ = TelemetrySharing.objects.get_or_create(driver=driver)
    return sharing


def _find_round(driver: DriverProfile, track: str, when) -> Round | None:
    rounds = list(
        Round.objects.filter(
            season__entries__driver=driver,
            scheduled_at__gte=when - MATCH_WINDOW,
            scheduled_at__lte=when + MATCH_WINDOW,
            track_layout__track__key=track,
        ).distinct()
    )
    return rounds[0] if len(rounds) == 1 else None


def receive_lap(key: DriverKey, lap: dict) -> tuple[TelemetryLap, bool]:
    channels = lap["channels"]
    unknown = set(channels) - set(CHANNELS)
    if unknown or "t_ms" not in channels:
        raise TelemetryError("unknown_channels")
    lengths = {len(values) for values in channels.values()}
    if len(lengths) != 1 or not 0 < lengths.pop() <= MAX_SAMPLES:
        raise TelemetryError("bad_samples")
    content = json.dumps(channels, separators=(",", ":"), sort_keys=True).encode()
    sha256 = hashlib.sha256(
        content + f"{lap['recorded_at'].isoformat()}:{lap['lap_number']}".encode()
    ).hexdigest()
    existing = TelemetryLap.objects.filter(driver=key.driver, sha256=sha256).first()
    if existing:
        return existing, False
    track = track_key(lap["track"])
    item = TelemetryLap(
        driver=key.driver,
        round=_find_round(key.driver, track, lap["recorded_at"]),
        sha256=sha256,
        session_type=lap.get("session_type", "")[:12],
        track=track[:100],
        car=lap["car"][:100],
        lap_number=lap["lap_number"],
        lap_time_ms=lap["lap_time_ms"],
        valid=lap.get("valid", True),
        recorded_at=lap["recorded_at"],
        sample_hz=lap["sample_hz"],
        uploaded_by=key.driver.user,
    )
    item.samples.save("samples.json", ContentFile(content), save=False)
    with transaction.atomic():
        item.save()
    return item, True


def _teammates(viewer_driver: DriverProfile | None, lap: TelemetryLap) -> bool:
    if viewer_driver is None or lap.round is None:
        return False
    season = lap.round.season
    theirs = SeasonEntry.objects.filter(season=season, driver=lap.driver).first()
    mine = SeasonEntry.objects.filter(season=season, driver=viewer_driver).first()
    return bool(theirs and mine and theirs.team and theirs.team == mine.team)


def access(viewer, lap: TelemetryLap) -> str | None:
    """The access level of the viewer to the lap."""
    if not viewer.is_authenticated:
        return None
    viewer_driver = getattr(viewer, "driver_profile", None)
    if viewer_driver is not None and viewer_driver.pk == lap.driver_id:
        return Access.FULL
    if lap.round is None:
        return None  # A lap without a round belongs only to its driver.
    championship = lap.round.season.championship
    if not can_view(viewer, championship):
        return None
    sharing = sharing_for(lap.driver)
    # Other drivers never get more than lap times and speed.
    levels = [Access.LAPS if sharing.drivers != Access.NONE else Access.NONE]
    if _teammates(viewer_driver, lap):
        levels.append(sharing.teammates)
    if can_manage(viewer, championship):
        levels.append(sharing.admins)
    best = max(levels, key=lambda level: RANK[level])
    return None if best == Access.NONE else best


def channels_for(lap: TelemetryLap, level: str) -> dict:
    with lap.samples.open("rb") as handle:
        channels = json.loads(handle.read())
    if level == Access.FULL:
        return channels
    return {name: values for name, values in channels.items() if name in PUBLIC_CHANNELS}
