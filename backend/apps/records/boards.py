"""Track record boards. Pure functions with no database.

A board is one exact track layout, one car, and one category (qualifying or race). The app
calculates the boards from the laps each time, so a correction always gives the right record.
A lap that is not eligible any more stays in the history with its reason.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RecordLap:
    lap_id: int
    layout_id: int
    car_id: int
    category: str  # "qualifying" or "race"
    lap_time_ms: int
    entry_id: int
    driver_name: str
    round_id: int
    round_number: int
    date: datetime
    timestamp_ms: int
    ineligible_reason: str | None = None  # None means the lap can be a record.
    season_id: int = 0  # 0 for a manual record, which has no season.


@dataclass
class HistoryItem:
    lap: RecordLap
    kind: str  # "record", "equal", or "removed"


@dataclass
class Board:
    layout_id: int
    car_id: int
    category: str
    record_ms: int | None = None
    holders: list[RecordLap] = field(default_factory=list)
    history: list[HistoryItem] = field(default_factory=list)
    # The best eligible lap of each driver, fastest first.
    ranking: list[RecordLap] = field(default_factory=list)


def _order(lap: RecordLap):
    return (lap.date, lap.round_number, lap.timestamp_ms, lap.lap_id)


def board(laps: Iterable[RecordLap]) -> list[HistoryItem]:
    """The history of one board, in time order. The last record items are the holders."""
    history: list[HistoryItem] = []
    best: int | None = None
    holders: set[int] = set()
    for lap in sorted(laps, key=_order):
        if lap.ineligible_reason:
            if best is None or lap.lap_time_ms <= best:
                history.append(HistoryItem(lap, "removed"))
            continue
        if best is None or lap.lap_time_ms < best:
            best = lap.lap_time_ms
            holders = {lap.entry_id}
            history.append(HistoryItem(lap, "record"))
        elif lap.lap_time_ms == best and lap.entry_id not in holders:
            holders.add(lap.entry_id)
            history.append(HistoryItem(lap, "equal"))
    return history


def ranking(laps: Iterable[RecordLap]) -> list[RecordLap]:
    """The best eligible lap of each driver, fastest first. With equal times, the earlier lap
    is first."""
    best: dict[str, RecordLap] = {}
    for lap in sorted(laps, key=_order):
        if lap.ineligible_reason:
            continue
        old = best.get(lap.driver_name)
        if old is None or lap.lap_time_ms < old.lap_time_ms:
            best[lap.driver_name] = lap
    return sorted(best.values(), key=lambda lap: (lap.lap_time_ms, _order(lap)))


def boards(laps: Iterable[RecordLap], overall: bool = False) -> list[Board]:
    """One board for each layout, car, and category. With overall, one board for each layout
    and category: the car does not count, and the board has car ID 0."""
    groups: dict[tuple[int, int, str], list[RecordLap]] = {}
    for lap in laps:
        car_id = 0 if overall else lap.car_id
        groups.setdefault((lap.layout_id, car_id, lap.category), []).append(lap)
    result = []
    for (layout_id, car_id, category), group in groups.items():
        history = board(group)
        records = [item for item in history if item.kind in ("record", "equal")]
        item = Board(layout_id, car_id, category, history=history, ranking=ranking(group))
        if records:
            item.record_ms = min(i.lap.lap_time_ms for i in records)
            item.holders = [i.lap for i in records if i.lap.lap_time_ms == item.record_ms]
        result.append(item)
    return sorted(result, key=lambda b: (b.layout_id, b.category, b.record_ms or 0))
