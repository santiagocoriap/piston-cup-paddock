"""Collection health of a championship: collector status, missing data, and failed tasks.

Each problem has its own code, so the page can show a different message for a stopped
collector, partial events, and missing sectors.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from apps.competition.models import Championship, Round, Session
from apps.imports.models import ImportedLap, PenaltyLogFile, ResultImport
from apps.reports.models import RaceReport

from .models import CollectorEvent, CollectorFile, CollectorToken

STOPPED_AFTER = timedelta(minutes=15)  # The collector pings every 5 minutes.
# The collector runs only on a race night. "stopped" is a problem only near a race start.
RACE_TIME = timedelta(hours=3)
ROUND_WINDOW = timedelta(hours=12)
RECENT_ROUNDS = 6


@dataclass
class CollectorHealth:
    id: int
    name: str
    status: str  # "running", "stopped", "never", or "revoked"
    last_seen_at: object
    last_file_at: object
    last_event_at: object
    version: str = ""
    latest_version: str = ""  # The newest release. The collector updates to it at its start.
    queued_files: int = 0
    last_error: str = ""
    last_error_at: object = None


@dataclass
class RoundHealth:
    id: int
    number: int
    season_name: str
    track_name: str
    scheduled_at: object
    problems: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class FailedTask:
    kind: str  # "report"
    id: int
    label: str
    error: str
    at: object


@dataclass
class Health:
    collectors: list[CollectorHealth]
    rounds: list[RoundHealth]
    failed: list[FailedTask]
    unmatched_files: int


def collector_status(token: CollectorToken, now, race_now: bool = True) -> str:
    """ "off" is normal: the collector runs only on a race night. "stopped" is a collector that
    does not run near the start of a race."""
    if token.revoked_at:
        return "revoked"
    if token.last_seen_at is None:
        return "never"
    if now - token.last_seen_at <= STOPPED_AFTER:
        return "running"
    return "stopped" if race_now else "off"


def race_now(championship: Championship, now) -> bool:
    return Round.objects.filter(
        season__championship=championship,
        scheduled_at__gte=now - RACE_TIME,
        scheduled_at__lte=now + RACE_TIME,
    ).exists()


def _round_health(round_: Round, tokens: list[CollectorToken]) -> RoundHealth:
    item = RoundHealth(
        id=round_.id,
        number=round_.number,
        season_name=round_.season.name,
        track_name=round_.track_layout.track.name,
        scheduled_at=round_.scheduled_at,
    )
    race_import = (
        ResultImport.objects.filter(
            round=round_, session__kind=Session.Kind.RACE, status=ResultImport.State.APPLIED
        )
        .order_by("-applied_at")
        .first()
    )
    if race_import is None:
        item.problems.append("no_race_file")
    else:
        laps = ImportedLap.objects.filter(result_import=race_import, entry__isnull=False)
        missing = sum(1 for lap in laps.only("sectors_ms") if not lap.sectors_ms)
        item.counts["laps"] = laps.count()
        if missing:
            item.problems.append("missing_sectors")
            item.counts["laps_without_sectors"] = missing
    if not PenaltyLogFile.objects.filter(round=round_).exists():
        item.problems.append("no_penalty_logs")

    if tokens and round_.scheduled_at:
        start = round_.scheduled_at - ROUND_WINDOW
        end = round_.scheduled_at + ROUND_WINDOW
        events = CollectorEvent.objects.filter(
            token__in=tokens, occurred_at__gte=start, occurred_at__lte=end
        )
        files = CollectorFile.objects.filter(token__in=tokens, round=round_)
        item.counts["events"] = events.count()
        item.counts["collector_files"] = files.count()
        if not events.exists() and not files.exists():
            item.problems.append("collector_stopped")
        elif not events.exists():
            item.problems.append("no_events")
        elif race_import is not None:
            lap_events = events.filter(kind="lap_completed").count()
            if lap_events < item.counts.get("laps", 0):
                item.problems.append("partial_events")
                item.counts["lap_events"] = lap_events
    elif not tokens:
        item.problems.append("no_collector")
    return item


def championship_health(championship: Championship) -> Health:
    from .release import latest

    now = timezone.now()
    tokens = list(championship.collectors.all())
    racing = race_now(championship, now)
    newest = latest()
    collectors = []
    for token in tokens:
        last_file = token.files.order_by("-received_at").values_list("received_at", flat=True)
        last_event = token.events.order_by("-received_at").values_list("received_at", flat=True)
        collectors.append(
            CollectorHealth(
                id=token.id,
                name=token.name,
                status=collector_status(token, now, racing),
                last_seen_at=token.last_seen_at,
                last_file_at=last_file.first(),
                last_event_at=last_event.first(),
                version=token.version,
                latest_version=newest.version if newest else "",
                queued_files=token.queued_files,
                last_error=token.last_error,
                last_error_at=token.last_error_at,
            )
        )
    active = [t for t in tokens if not t.revoked_at]
    rounds = (
        Round.objects.filter(season__championship=championship, scheduled_at__lte=now)
        .select_related("season", "track_layout__track")
        .order_by("-scheduled_at")[:RECENT_ROUNDS]
    )
    failed = [
        FailedTask(
            kind="report",
            id=report.id,
            label=(
                f"{report.season.name} R{report.round.number}"
                if report.round
                else report.season.name
            ),
            error=report.error,
            at=report.generated_at,
        )
        for report in RaceReport.objects.filter(
            season__championship=championship, status=RaceReport.State.FAILED
        ).select_related("season", "round")[:20]
    ]
    return Health(
        collectors=collectors,
        rounds=[_round_health(r, active) for r in rounds],
        failed=failed,
        unmatched_files=CollectorFile.objects.filter(
            token__championship=championship, status=CollectorFile.State.UNMATCHED
        ).count(),
    )
