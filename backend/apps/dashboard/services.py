"""The data that a driver needs first: position, points, recent results, and the next round."""

from dataclasses import dataclass, field
from datetime import datetime

from apps.competition.models import Round, SeasonEntry
from apps.competition.permissions import can_view
from apps.handicaps.models import UsedHandicap
from apps.handicaps.services import season_handicaps
from apps.reports.services import latest_ready, read_ids
from apps.results.services import season_standings


@dataclass
class RecentResult:
    round_id: int
    round_number: int
    track_name: str
    status: str
    position: int | None
    points: int


@dataclass
class NewReport:
    round_id: int
    round_number: int
    track_name: str


@dataclass
class NextRound:
    round_id: int
    round_number: int
    track_name: str
    layout_name: str
    scheduled_at: datetime | None
    event_timezone: str
    ballast_kg: int
    restrictor_pct: int
    my_attendance: str | None = None
    attending: int = 0  # Drivers who answered yes.
    # The values the driver carried into the last race. None before the first race.
    previous_ballast_kg: int | None = None
    previous_restrictor_pct: int | None = None
    # The conditions an admin announced for the round. None when nothing is announced.
    conditions: dict | None = None
    # Pictures from the game files. None until an admin imports them.
    track_outline_url: str | None = None
    track_preview_url: str | None = None
    car_image_url: str | None = None


@dataclass
class SeasonCard:
    season_id: int
    season_name: str
    championship_name: str
    entry_number: int
    car_name: str
    rank: int
    entries: int
    points: int
    wins: int
    leader_points: int
    recent: list[RecentResult] = field(default_factory=list)
    next_round: NextRound | None = None
    new_reports: list[NewReport] = field(default_factory=list)


def driver_dashboard(user) -> list[SeasonCard]:
    entries = (
        SeasonEntry.objects.filter(driver__user=user)
        .select_related("season__championship__league", "car")
        .order_by("-season__created_at")
    )
    cards = []
    for entry in entries:
        season = entry.season
        if not can_view(user, season.championship):
            continue
        table = season_standings(season)
        row = next((r for r in table if r.entry_id == entry.id), None)
        if row is None:
            continue
        rounds = {r.id: r for r in season.rounds.select_related("track_layout__track")}
        by_number = {r.number: r for r in rounds.values()}
        recent = [
            RecentResult(
                round_id=by_number[score.round_number].id,
                round_number=score.round_number,
                track_name=by_number[score.round_number].track_layout.track.name,
                status=score.status,
                position=score.position,
                points=score.points,
            )
            for score in reversed(row.rounds)
            if score.status is not None
        ][:3]
        card = SeasonCard(
            season_id=season.id,
            season_name=season.name,
            championship_name=season.championship.name,
            entry_number=entry.number,
            car_name=entry.car.name,
            rank=row.rank,
            entries=len(table),
            points=row.points,
            wins=row.wins,
            leader_points=table[0].points if table else 0,
            recent=recent,
        )
        reports = latest_ready(rounds.keys())
        read = read_ids(user, reports.values())
        card.new_reports = [
            NewReport(
                r.round_id, rounds[r.round_id].number, rounds[r.round_id].track_layout.track.name
            )
            for r in sorted(reports.values(), key=lambda r: -rounds[r.round_id].number)
            if r.id not in read
        ]
        handicaps = season_handicaps(season)
        if handicaps.next_round_id:
            next_round = rounds[handicaps.next_round_id]
            mine = next(e for e in handicaps.entries if e.entry_id == entry.id)
            card.next_round = NextRound(
                round_id=next_round.id,
                round_number=next_round.number,
                track_name=next_round.track_layout.track.name,
                layout_name=next_round.track_layout.name,
                scheduled_at=next_round.scheduled_at,
                event_timezone=season.championship.league.timezone,
                ballast_kg=mine.next_kg,
                restrictor_pct=mine.next_pct,
                my_attendance=next_round.attendance.filter(entry=entry)
                .values_list("answer", flat=True)
                .first(),
                attending=next_round.attendance.filter(answer="yes").count(),
                conditions=_announced(next_round),
                track_outline_url=next_round.track_layout.image_url("outline"),
                track_preview_url=next_round.track_layout.image_url("preview"),
                car_image_url=entry.car.image_url("preview"),
            )
            if mine.rounds:
                last = mine.rounds[-1]
                if last.used_kg is not None:
                    previous = (last.used_kg, last.used_pct)
                else:
                    before = season_handicaps(season, before_round=rounds[last.round_id])
                    carried = next(e for e in before.entries if e.entry_id == entry.id)
                    previous = (carried.next_kg, carried.next_pct)
                card.next_round.previous_ballast_kg, card.next_round.previous_restrictor_pct = (
                    previous
                )
        cards.append(card)
    return cards


CONDITION_KEYS = ("time_of_day", "weather", "air_temp_c", "track_temp_c", "grip")


def _announced(round_: Round) -> dict | None:
    announced = round_.announced_conditions or {}
    values = {key: announced.get(key) for key in CONDITION_KEYS}
    if not any(value not in (None, "") for value in values.values()):
        return None
    return values


@dataclass
class MyHandicap:
    entry_number: int
    car_name: str
    ballast_kg: int
    restrictor_pct: int
    source: str  # "used": the values of the race. "assigned": the values for a future race.


def my_handicap(user, round_: Round) -> MyHandicap | None:
    """The ballast and restrictor of the signed-in driver for this round."""
    entry = (
        SeasonEntry.objects.filter(season=round_.season, driver__user=user)
        .select_related("car")
        .first()
    )
    if entry is None:
        return None
    used = UsedHandicap.objects.filter(round=round_, entry=entry).first()
    if used:
        return MyHandicap(
            entry.number, entry.car.name, used.ballast_kg, used.restrictor_pct, "used"
        )
    values = season_handicaps(round_.season, before_round=round_)
    mine = next(e for e in values.entries if e.entry_id == entry.id)
    return MyHandicap(entry.number, entry.car.name, mine.next_kg, mine.next_pct, "assigned")
