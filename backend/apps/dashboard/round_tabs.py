"""How much data each tab of a round page has. The page shows the count on the tab, and grays out
a tab with no data. The counts use the same rules as the tabs, so a count never shows data that
the tab hides."""

from dataclasses import dataclass

from apps.collectors.incident_api import WINDOW, collisions
from apps.collectors.models import CollectorEvent
from apps.collectors.replay_api import RACE
from apps.competition.models import Round, Session
from apps.imports.lap_services import _applied_import
from apps.imports.models import ImportedLap
from apps.reports.models import RaceReport
from apps.restarts.models import Restart
from apps.telemetry.services import access


@dataclass
class TabCounts:
    laps: int
    incidents: int
    replay: int
    restarts: int
    telemetry: int
    reports: int


def _race_starts(round_: Round) -> int:
    """The race starts that the collector saw. The replay shows one start at a time."""
    if round_.scheduled_at is None:
        return 0
    events = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
        kind="session_started",
    )
    return sum(1 for event in events if (event.data or {}).get("type") == RACE)


def tab_counts(viewer, round_: Round) -> TabCounts:
    race_import = _applied_import(round_, Session.Kind.RACE)
    laps = (
        ImportedLap.objects.filter(result_import=race_import, entry__isnull=False).count()
        if race_import
        else 0
    )
    found, _, _ = collisions(round_, "race")
    restarts = Restart.objects.filter(
        abandoned_attempt__session__round=round_,
        abandoned_attempt__session__kind=Session.Kind.RACE,
    ).count()
    telemetry = sum(
        1
        for lap in round_.telemetry_laps.select_related("driver", "round__season__championship")
        if access(viewer, lap)
    )
    reports = round_.reports.filter(status=RaceReport.State.READY).count()
    return TabCounts(
        laps=laps,
        incidents=len(found),
        replay=_race_starts(round_),
        restarts=restarts,
        telemetry=telemetry,
        reports=reports,
    )
