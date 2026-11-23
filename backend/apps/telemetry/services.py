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

from apps.competition.models import SeasonEntry
from apps.competition.permissions import can_manage, can_view
from apps.identity.models import DriverProfile

from .models import Access, TelemetryLap, TelemetrySharing
from .samples import read_samples

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
        channels = read_samples(handle)
    if level == Access.FULL:
        return channels
    return {name: values for name, values in channels.items() if name in PUBLIC_CHANNELS}


# A lap of the script and a lap of the result file with this lap time are the same lap.
OFFICIAL_LAP_MS = 1


def official_numbers(round_) -> dict[int, tuple[int, bool]]:
    """For each script lap of the round: the lap number and the validity from the applied
    result file of its session. The file is the truth: a lost server lap in the collector
    data shifts the count of the server laps, not the file.

    The file has the laps of the final start only. So a lap of an earlier start, or a lap
    with no lap of the same time in the file, keeps its own number."""
    from apps.imports.models import ImportedLap, ResultImport

    found: dict[int, tuple[int, bool]] = {}
    laps = list(round_.telemetry_laps.select_related("driver"))
    for session_type in {lap.session_type for lap in laps}:
        applied = (
            ResultImport.objects.filter(
                round=round_, session__kind=session_type, status=ResultImport.State.APPLIED
            )
            .order_by("-applied_at")
            .first()
        )
        if applied is None:
            continue
        by_guid: dict[str, list] = {}
        for row in ImportedLap.objects.filter(result_import=applied):
            by_guid.setdefault(row.guid, []).append(row)
        last_attempt = last_start(laps).get(session_type, 0)
        for lap in laps:
            if lap.session_type != session_type or (lap.attempt_number or 0) != last_attempt:
                continue
            same = [
                row
                for guid in lap.driver.guids()
                for row in by_guid.get(guid, [])
                if abs(row.lap_time_ms - lap.lap_time_ms) <= OFFICIAL_LAP_MS
            ]
            if len(same) == 1:
                found[lap.id] = (same[0].lap_number, same[0].cuts == 0)
    return found


def last_start(laps) -> dict[str, int]:
    """For each session type: the number of the last start. A race restart makes a new start,
    and only the laps of the last start count. A session with no start numbers gives 0."""
    found: dict[str, int] = {}
    for lap in laps:
        found[lap.session_type] = max(found.get(lap.session_type, 0), lap.attempt_number or 0)
    return found


def final_laps(round_, session: str) -> list[TelemetryLap]:
    """The script laps of the session that count: only the laps of the last start. Each lap
    gets the lap number and the validity of the result file when the file has the lap."""
    laps = [
        lap
        for lap in round_.telemetry_laps.select_related("driver", "round__season__championship")
        if lap.session_type == session
    ]
    last = last_start(laps).get(session, 0)
    official = official_numbers(round_)
    kept = []
    for lap in laps:
        if (lap.attempt_number or 0) != last:
            continue
        if lap.id in official:
            lap.lap_number, lap.valid = official[lap.id]
        kept.append(lap)
    return kept
