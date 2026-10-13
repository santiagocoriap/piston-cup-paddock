"""Lap tables: best values, averages, and the theoretical lap. Pure functions with no database.

A valid lap has no cuts and no invalid reason. Only valid laps give best values, averages,
and theoretical sectors. "personal" marks the best value of a driver. "session" marks the best
value of the session. A session best is also the personal best of that driver.
"""

from dataclasses import dataclass, field

# The laps that the clean average leaves out, in the order the app shows them.
CLEAN_RULES = ["invalid", "pit_in", "pit_out", "first_lap"]
CONTACT_RULE = "contact"  # Added only when the round has collector incident data.


def clean_rules_for(race: bool, contacts: bool) -> list[str]:
    rules = CLEAN_RULES if race else CLEAN_RULES[:3]
    return [*rules, CONTACT_RULE] if contacts else list(rules)


@dataclass
class LapRow:
    lap_number: int
    time_ms: int
    sectors_ms: list[int]
    cuts: int = 0
    invalid_reason: str = ""
    tyre: str = ""
    pit: str | None = None  # "in", "out", or None
    contact: bool = False  # The driver had an incident on this lap.

    @property
    def valid(self) -> bool:
        return self.cuts == 0 and not self.invalid_reason


@dataclass
class MarkedLap:
    row: LapRow
    time_mark: str | None = None
    sector_marks: list[str | None] = field(default_factory=list)


@dataclass
class Average:
    ms: int | None
    laps: int  # The laps in the average.
    excluded: dict[str, int]  # The laps left out, by rule.


@dataclass
class DriverLaps:
    key: object
    laps: list[MarkedLap]
    best_lap_ms: int | None
    best_lap_number: int | None
    average: Average
    clean_average: Average
    theoretical_ms: int | None  # The sum of the best valid sectors. None if a sector is missing.
    best_sectors_ms: list[int | None]


def _sector_count(rows: list[LapRow]) -> int:
    return max((len(r.sectors_ms) for r in rows), default=0)


def _best_sectors(rows: list[LapRow], count: int) -> list[int | None]:
    best: list[int | None] = [None] * count
    for row in rows:
        if not row.valid:
            continue
        for index, value in enumerate(row.sectors_ms):
            if value > 0 and (best[index] is None or value < best[index]):
                best[index] = value
    return best


def _average(rows: list[LapRow], rules: list[str]) -> Average:
    excluded = {rule: 0 for rule in rules}
    included = []
    for row in rows:
        reason = _exclusion(row, rules)
        if reason:
            excluded[reason] += 1
        else:
            included.append(row.time_ms)
    ms = round(sum(included) / len(included)) if included else None
    return Average(ms, len(included), excluded)


def _exclusion(row: LapRow, rules: list[str]) -> str | None:
    """The first rule that leaves the lap out, or None."""
    checks = {
        "invalid": not row.valid,
        "pit_in": row.pit == "in",
        "pit_out": row.pit == "out",
        "first_lap": row.lap_number == 1,
        CONTACT_RULE: row.contact,
    }
    return next((rule for rule in rules if checks[rule]), None)


def analyze(
    drivers: dict[object, list[LapRow]], *, race: bool, contacts: bool = False
) -> list[DriverLaps]:
    """Mark best values and compute averages for each driver. The first lap of a race is a
    standing start, so the clean average of a race leaves it out."""
    all_rows = [row for rows in drivers.values() for row in rows]
    count = _sector_count(all_rows)
    valid = [row for row in all_rows if row.valid]
    session_lap = min((r.time_ms for r in valid), default=None)
    session_sectors = _best_sectors(all_rows, count)
    clean_rules = clean_rules_for(race, contacts)

    result = []
    for key, rows in drivers.items():
        rows = sorted(rows, key=lambda r: r.lap_number)
        mine = [r for r in rows if r.valid]
        best = min(mine, key=lambda r: r.time_ms) if mine else None
        sectors = _best_sectors(rows, count)
        marked = []
        for row in rows:
            lap = MarkedLap(row)
            if row.valid and best and row.time_ms == best.time_ms:
                lap.time_mark = "session" if row.time_ms == session_lap else "personal"
            for index in range(count):
                value = row.sectors_ms[index] if index < len(row.sectors_ms) else None
                mark = None
                if row.valid and value and value == sectors[index]:
                    mark = "session" if value == session_sectors[index] else "personal"
                lap.sector_marks.append(mark)
            marked.append(lap)
        theoretical = sum(sectors) if count and all(s is not None for s in sectors) else None
        result.append(
            DriverLaps(
                key=key,
                laps=marked,
                best_lap_ms=best.time_ms if best else None,
                best_lap_number=best.lap_number if best else None,
                average=_average(rows, ["invalid"]),
                clean_average=_average(rows, clean_rules),
                theoretical_ms=theoretical,
                best_sectors_ms=sectors,
            )
        )
    return result
