"""Points and standings. Pure functions with no database, so the league rules are easy to test.

The rules come from docs/LEAGUE_RULES.md.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

LEAGUE_POINTS: tuple[int, ...] = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)


class Status(StrEnum):
    FINISHED = "finished"
    DNF = "dnf"
    DNS = "dns"
    DSQ = "dsq"


CLASSIFIED = {Status.FINISHED, Status.DNF}


@dataclass(frozen=True)
class PointsRules:
    points_by_position: Sequence[int]
    pole_bonus: int = 0
    fastest_lap_bonus: int = 0

    def points_for(self, position: int) -> int:
        table = self.points_by_position
        return table[position - 1] if 1 <= position <= len(table) else 0


@dataclass(frozen=True)
class Line:
    """One entry in the result of one race."""

    entry_id: int
    status: Status
    position: int | None
    pole: bool = False
    fastest_lap: bool = False


class ResultError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate(lines: Sequence[Line]) -> None:
    """Raise ResultError when the result breaks a rule. The code names the rule."""
    entry_ids = [line.entry_id for line in lines]
    if len(entry_ids) != len(set(entry_ids)):
        raise ResultError("duplicate_entry")
    for line in lines:
        if line.status in CLASSIFIED and line.position is None:
            raise ResultError("position_required")
        if line.status not in CLASSIFIED and line.position is not None:
            raise ResultError("position_not_allowed")
        if line.status == Status.DNS and (line.pole or line.fastest_lap):
            raise ResultError("dns_has_no_bonus")
    positions = sorted(line.position for line in lines if line.position is not None)
    if positions != list(range(1, len(positions) + 1)):
        raise ResultError("positions_not_continuous")
    if sum(line.pole for line in lines) > 1:
        raise ResultError("one_pole_only")
    if sum(line.fastest_lap for line in lines) > 1:
        raise ResultError("one_fastest_lap_only")


def race_points(lines: Sequence[Line], rules: PointsRules) -> dict[int, int]:
    """Give the points of each entry in one race.

    A classified driver (finished or DNF) gets the points of their position.
    A DNS driver gets 0. A DSQ driver gets the points of the last position of the race,
    which is the number of starters, and loses the bonuses.
    """
    starters = sum(1 for line in lines if line.status != Status.DNS)
    points: dict[int, int] = {}
    for line in lines:
        if line.status in CLASSIFIED:
            total = rules.points_for(line.position)
        elif line.status == Status.DSQ:
            total = rules.points_for(starters)
        else:
            total = 0
        if line.status != Status.DSQ:
            total += rules.pole_bonus if line.pole else 0
            total += rules.fastest_lap_bonus if line.fastest_lap else 0
        points[line.entry_id] = total
    return points


@dataclass
class StandingRow:
    entry_id: int
    points: int = 0
    rank: int = 0
    finishes: Counter = field(default_factory=Counter)

    @property
    def wins(self) -> int:
        return self.finishes[1]


def standings(
    entry_ids: Iterable[int], races: Iterable[tuple[Sequence[Line], dict[int, int]]]
) -> list[StandingRow]:
    """Order the season. Equal points go to the driver with more wins, then more 2nd places,
    and so on. Drivers with equal points and equal counts share the position."""
    rows = {entry_id: StandingRow(entry_id) for entry_id in entry_ids}
    deepest = 0
    for lines, points in races:
        for line in lines:
            row = rows.setdefault(line.entry_id, StandingRow(line.entry_id))
            row.points += points.get(line.entry_id, 0)
            if line.status in CLASSIFIED:
                row.finishes[line.position] += 1
                deepest = max(deepest, line.position)

    def key(row: StandingRow) -> tuple:
        return (row.points, *(row.finishes[p] for p in range(1, deepest + 1)))

    ordered = sorted(rows.values(), key=key, reverse=True)
    for index, row in enumerate(ordered):
        same_as_previous = index > 0 and key(row) == key(ordered[index - 1])
        row.rank = ordered[index - 1].rank if same_as_previous else index + 1
    return ordered
