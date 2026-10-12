from dataclasses import dataclass

from django.db import transaction

from apps.audit.services import change, record
from apps.competition.attempts import accept_current_attempt
from apps.competition.models import Round, Season
from apps.rules.models import RulesVersion
from apps.rules.scoring import Line, ResultError, Status, race_points, standings, validate

from .models import RaceResult, ResultLine


def save_result(round_: Round, lines: list[Line], user, reason: str = "") -> RaceResult:
    """Check the lines, calculate the points, and replace the result of the round."""
    entry_ids = set(round_.season.entries.values_list("id", flat=True))
    if any(line.entry_id not in entry_ids for line in lines):
        raise ResultError("entry_not_in_season")
    validate(lines)

    rules_version = RulesVersion.current_for(round_.season)
    points = race_points(lines, rules_version.as_points_rules())
    with transaction.atomic():
        before = {
            row.entry_id: row
            for row in ResultLine.objects.filter(result__round=round_).select_related(
                "entry__driver"
            )
        }
        result, _ = RaceResult.objects.update_or_create(
            round=round_, defaults={"rules_version": rules_version, "updated_by": user}
        )
        result.lines.all().delete()
        ResultLine.objects.bulk_create(
            ResultLine(
                result=result,
                entry_id=line.entry_id,
                status=line.status,
                position=line.position,
                pole=line.pole,
                fastest_lap=line.fastest_lap,
                points=points[line.entry_id],
            )
            for line in lines
        )
        accept_current_attempt(round_)  # Points come only from the accepted attempt.
        _audit_result(round_, user, reason, before, lines, points)
    return result


def _audit_result(round_, user, reason, before, lines, points) -> None:
    drivers = dict(round_.season.entries.values_list("id", "driver__display_name"))
    after = {line.entry_id: line for line in lines}
    changes = []
    for entry_id in sorted(set(before) | set(after), key=lambda e: drivers.get(e, "")):
        old = before.get(entry_id)
        new = after.get(entry_id)
        old_value = (
            {"status": old.status, "position": old.position, "points": old.points} if old else None
        )
        new_value = (
            {"status": new.status, "position": new.position, "points": points[entry_id]}
            if new
            else None
        )
        if old_value != new_value:
            changes.append(change(drivers.get(entry_id, str(entry_id)), old_value, new_value))
    record(
        user,
        "result.saved" if not before else "result.changed",
        "round",
        round_.id,
        championship=round_.season.championship,
        params={
            "season": round_.season.name,
            "number": round_.number,
            "track": str(round_.track_layout),
        },
        changes=changes,
        reason=reason,
    )


def _as_line(row: ResultLine) -> Line:
    return Line(row.entry_id, Status(row.status), row.position, row.pole, row.fastest_lap)


@dataclass
class RoundScore:
    round_number: int
    status: str | None
    position: int | None
    points: int


@dataclass
class SeasonStanding:
    rank: int
    entry_id: int
    points: int
    wins: int
    rounds: list[RoundScore]


def season_standings(season: Season) -> list[SeasonStanding]:
    """The standings from the stored points of each round result."""
    rounds = list(season.rounds.order_by("number"))
    lines_by_round: dict[int, list[ResultLine]] = {r.id: [] for r in rounds}
    for row in ResultLine.objects.filter(result__round__season=season).select_related("result"):
        lines_by_round[row.result.round_id].append(row)

    races = [
        ([_as_line(row) for row in rows], {row.entry_id: row.points for row in rows})
        for rows in lines_by_round.values()
        if rows
    ]
    entry_ids = list(season.entries.values_list("id", flat=True))
    table = standings(entry_ids, races)

    def score(round_: Round, entry_id: int) -> RoundScore:
        row = next((r for r in lines_by_round[round_.id] if r.entry_id == entry_id), None)
        if row is None:
            return RoundScore(round_.number, None, None, 0)
        return RoundScore(round_.number, row.status, row.position, row.points)

    return [
        SeasonStanding(
            rank=row.rank,
            entry_id=row.entry_id,
            points=row.points,
            wins=row.wins,
            rounds=[score(r, row.entry_id) for r in rounds],
        )
        for row in table
    ]
