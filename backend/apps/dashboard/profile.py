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
from apps.results.services import career_points, season_standings

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


def seasons(user, driver: DriverProfile) -> list[SeasonRow]:
    rows = []
    entries = (
        SeasonEntry.objects.filter(driver=driver)
        .select_related("season__championship")
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
            )
        )
    return rows


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
                    car=lap.entry.car.name,
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
            review_status=Restart.Review.CONFIRMED,
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
