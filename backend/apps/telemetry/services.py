"""Driver telemetry: decide who sees what. The laps come from the Paddock script
(script.py).

Access levels:
- "full": every channel, with the driver inputs.
- "laps": lap time, track position, and speed. No inputs.
- None: nothing.

The driver always has full access. The driver chooses the level for teammates, for other
drivers, and for admins. "none" is the default for other drivers. Basic results never need
telemetry.
"""

import json

from apps.competition.models import SeasonEntry
from apps.competition.permissions import can_manage, can_view
from apps.identity.models import DriverProfile

from .models import Access, TelemetryLap, TelemetrySharing

# The "laps" level gets only these. The other channels (gas, brake, steer, gear, rpm) are the
# driver inputs: only the "full" level gets them.
PUBLIC_CHANNELS = ["t_ms", "pos", "speed_kmh"]
RANK = {None: 0, Access.NONE: 0, Access.LAPS: 1, Access.FULL: 2}


class TelemetryError(ValueError):
    pass


def sharing_for(driver: DriverProfile) -> TelemetrySharing:
    sharing, _ = TelemetrySharing.objects.get_or_create(driver=driver)
    return sharing


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
    levels = [sharing.drivers]
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
