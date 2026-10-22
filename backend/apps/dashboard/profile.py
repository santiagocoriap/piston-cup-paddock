"""The driver profile: career level, results by season, safety, records, and restarts caused.

docs/LEAGUE_RULES.md, section "Career level", has the level rule.
"""

from dataclasses import dataclass, field

from django.db import transaction

from apps.audit.services import record
from apps.competition.models import Round, SeasonEntry
from apps.competition.permissions import can_view, is_league_admin, visible_championships
from apps.identity.models import CareerAdjustment, DriverProfile
from apps.records.services import record_boards
from apps.restarts.models import Restart
from apps.results.models import Penalty, ResultLine
from apps.results.services import career_points, season_standings

from .services import RecentResult

POINTS_PER_LEVEL = 100


def level_for(points: int) -> int:
    return 1 + max(points, 0) // POINTS_PER_LEVEL


@dataclass
class Career:
    raw_points: int  # All official points.
    points: int  # After resets and adjustments.
    level: int
    next_level_points: int
    adjustments: list[CareerAdjustment] = field(default_factory=list)


def career(driver: DriverProfile) -> Career:
    raw = career_points([driver.id])[driver.id]
    adjustments = list(driver.career_adjustments.select_related("created_by"))
    # A reset counts only the points after it: the official points since the reset, and the
    # adjustments after it.
    resets = [i for i, a in enumerate(adjustments) if a.kind == CareerAdjustment.Kind.RESET]
    start = resets[-1] if resets else -1
    points = raw - (adjustments[start].raw_points if resets else 0)
    points += sum(
        a.points for a in adjustments[start + 1 :] if a.kind == CareerAdjustment.Kind.ADJUST
    )
    level = level_for(points)
    return Career(raw, points, level, level * POINTS_PER_LEVEL, adjustments)


def adjust_career(driver: DriverProfile, user, kind: str, points: int, reason: str) -> None:
    raw = career_points([driver.id])[driver.id]
    with transaction.atomic():
        CareerAdjustment.objects.create(
            driver=driver,
            kind=kind,
            points=points if kind == CareerAdjustment.Kind.ADJUST else 0,
            raw_points=raw,
            reason=reason,
            created_by=user,
        )
        record(
            user,
            "career.adjusted",
            "driver",
            driver.id,
            params={"driver": driver.display_name, "kind": kind, "points": points},
            reason=reason,
        )


def can_see_driver(user, driver: DriverProfile) -> bool:
    if is_league_admin(user):
        return True
    if getattr(user, "driver_profile", None) and user.driver_profile.pk == driver.pk:
        return True
    return SeasonEntry.objects.filter(
        driver=driver, season__championship__in=visible_championships(user)
    ).exists()


@dataclass
class SeasonRow:
    season_id: int
    season_name: str
    championship_name: str
    rank: int
    entries: int
    points: int
    wins: int
    podiums: int
    starts: int
    # The entry of the driver in this season.
    number: int = 0
    car_name: str = ""
    team: str = ""
    # Every result of the season in round order, for the chips and the trend line.
    history: list[RecentResult] = field(default_factory=list)


def seasons(user, driver: DriverProfile) -> list[SeasonRow]:
    rows = []
    entries = (
        SeasonEntry.objects.filter(driver=driver)
        .select_related("season__championship", "car")
        .order_by("-season__created_at")
    )
    for entry in entries:
        season = entry.season
        if not can_view(user, season.championship):
            continue
        table = season_standings(season)
        mine = next((r for r in table if r.entry_id == entry.id), None)
        if mine is None:
            continue
        scores = [s for s in mine.rounds if s.status is not None]
        rounds = {r.number: r for r in season.rounds.select_related("track_layout__track")}
        rows.append(
            SeasonRow(
                season_id=season.id,
                season_name=season.name,
                championship_name=season.championship.name,
                rank=mine.rank,
                entries=len(table),
                points=mine.points,
                wins=mine.wins,
                podiums=sum(1 for s in scores if s.position and s.position <= 3),
                starts=sum(1 for s in scores if s.status != "dns"),
                number=entry.number,
                car_name=entry.car_name,
                team=entry.team,
                history=[
                    RecentResult(
                        round_id=rounds[s.round_number].id,
                        round_number=s.round_number,
                        track_name=rounds[s.round_number].track_layout.track.name,
                        status=s.status,
                        position=s.position,
                        points=s.points,
                    )
                    for s in scores
                    if s.round_number in rounds
                ],
            )
        )
    return rows


def current_lines(driver: DriverProfile, season_ids: list[int]) -> list[ResultLine]:
    """The lines of the driver in the current version of each result of these seasons."""
    lines = list(
        ResultLine.objects.filter(
            entry__driver=driver, entry__season_id__in=season_ids
        ).select_related("version")
    )
    latest: dict[int, int] = {}
    for line in lines:
        result_id = line.version.result_id
        latest[result_id] = max(latest.get(result_id, 0), line.version.number)
    return [line for line in lines if line.version.number == latest[line.version.result_id]]


@dataclass
class Stats:
    starts: int
    wins: int
    podiums: int
    top5: int
    poles: int
    fastest_laps: int
    best_finish: int | None
    average_finish: float | None  # The average place of the finished races.
    points: int
    laps: int
    records: int
    win_rate: float | None  # Wins per start, from 0 to 100.
    dnfs: int
    dsqs: int
    penalties: int
    incident_points: int
    restarts_caused: int


def stats(
    driver: DriverProfile,
    rows: list[SeasonRow],
    record_count: int,
    restart_count: int,
    incident_points: int,
) -> Stats:
    """The numbers of the career, from the seasons the viewer can see."""
    season_ids = [row.season_id for row in rows]
    lines = current_lines(driver, season_ids)
    started = [line for line in lines if line.status != "dns"]
    finished = [line.position for line in lines if line.status == "finished" and line.position]
    wins = sum(1 for line in lines if line.position == 1 and line.status == "finished")
    return Stats(
        starts=len(started),
        wins=wins,
        podiums=sum(1 for p in finished if p <= 3),
        top5=sum(1 for p in finished if p <= 5),
        poles=sum(line.pole for line in lines),
        fastest_laps=sum(line.fastest_lap for line in lines),
        best_finish=min(finished) if finished else None,
        average_finish=round(sum(finished) / len(finished), 1) if finished else None,
        points=sum(row.points for row in rows),
        laps=sum(line.laps or 0 for line in lines),
        records=record_count,
        win_rate=round(100 * wins / len(started)) if started else None,
        dnfs=sum(1 for line in lines if line.status == "dnf"),
        dsqs=sum(1 for line in lines if line.status == "dsq"),
        penalties=Penalty.objects.filter(
            entry__driver=driver, entry__season_id__in=season_ids
        ).count(),
        incident_points=incident_points,
        restarts_caused=restart_count,
    )


@dataclass
class Achievement:
    key: str  # "win", "podium", "pole", "fastest_lap", "starts", "record".
    count: int
    goal: int  # The count that unlocks the badge.

    @property
    def achieved(self) -> bool:
        return self.count >= self.goal


def achievements(
    driver: DriverProfile, rows: list[SeasonRow], record_count: int
) -> list[Achievement]:
    """The badges of the driver, from the seasons the viewer can see. Poles and fastest laps
    come from the current version of each result."""
    lines = current_lines(driver, [row.season_id for row in rows])
    poles = sum(line.pole for line in lines)
    fastest = sum(line.fastest_lap for line in lines)
    return [
        Achievement("win", sum(row.wins for row in rows), 1),
        Achievement("podium", sum(row.podiums for row in rows), 1),
        Achievement("pole", poles, 1),
        Achievement("fastest_lap", fastest, 1),
        Achievement("starts", sum(row.starts for row in rows), 10),
        Achievement("record", record_count, 1),
    ]


@dataclass
class RecordRow:
    track: str
    car: str
    category: str
    lap_time_ms: int
    round_id: int


def records(user, driver: DriverProfile) -> list[RecordRow]:
    entry_ids = set(driver.entries.values_list("id", flat=True))
    boards, details = record_boards(user)
    rows = []
    for board in boards:
        for holder in board.holders:
            if holder.entry_id not in entry_ids:
                continue
            lap = details[holder.lap_id]
            rows.append(
                RecordRow(
                    track=str(lap.result_import.round.track_layout),
                    car=lap.entry.car_name,
                    category=board.category,
                    lap_time_ms=holder.lap_time_ms,
                    round_id=holder.round_id,
                )
            )
    return rows


@dataclass
class RestartRow:
    round_id: int
    label: str
    attempt: int
    reason: str
    shared: bool


def restarts_caused(user, driver: DriverProfile) -> list[RestartRow]:
    items = (
        Restart.objects.filter(
            responsible_entries__driver=driver,
            review_status__in=[Restart.Review.CONFIRMED, Restart.Review.CORRECTED],
            abandoned_attempt__session__round__season__championship__in=visible_championships(user),
        )
        .select_related("abandoned_attempt__session__round__season")
        .prefetch_related("responsible_entries")
        .distinct()
    )
    rows = []
    for restart in items:
        round_: Round = restart.abandoned_attempt.session.round
        rows.append(
            RestartRow(
                round_id=round_.id,
                label=f"{round_.season.name} R{round_.number}",
                attempt=restart.abandoned_attempt.number,
                reason=restart.reason,
                shared=restart.responsible_entries.count() > 1,
            )
        )
    return rows
