"""Split the race laps of a driver into stints.

A new stint starts on the lap after a pit entry, or on a lap with another tyre than the lap
before it. Without Real Penalty logs, only a tyre change shows a stop, because the result file
has no pit data. A stop for fuel only on the same tyre is then not visible.
"""

from dataclasses import dataclass

from .lap_analysis import LapRow


@dataclass
class Stint:
    number: int
    first_lap: int
    last_lap: int
    laps: int
    tyre: str
    best_ms: int | None  # The best valid lap of the stint.
    average_ms: int | None  # Valid laps without the pit entry and the pit exit laps.
    ends_in_pit: bool


def split_stints(rows: list[LapRow]) -> list[Stint]:
    groups: list[list[LapRow]] = []
    for row in sorted(rows, key=lambda r: r.lap_number):
        last = groups[-1][-1] if groups else None
        new = last is None or last.pit == "in" or (row.tyre and last.tyre and row.tyre != last.tyre)
        if new:
            groups.append([row])
        else:
            groups[-1].append(row)
    stints = []
    for number, group in enumerate(groups, start=1):
        valid = [r.time_ms for r in group if r.valid]
        steady = [r.time_ms for r in group if r.valid and r.pit is None]
        stints.append(
            Stint(
                number=number,
                first_lap=group[0].lap_number,
                last_lap=group[-1].lap_number,
                laps=len(group),
                tyre=next((r.tyre for r in group if r.tyre), ""),
                best_ms=min(valid) if valid else None,
                average_ms=round(sum(steady) / len(steady)) if steady else None,
                ends_in_pit=group[-1].pit == "in",
            )
        )
    return stints
