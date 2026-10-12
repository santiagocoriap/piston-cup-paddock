from datetime import UTC, datetime

from apps.records.boards import RecordLap, board, boards


def lap(lap_id, time, entry, day, reason=None, category="race", car=1):
    return RecordLap(
        lap_id=lap_id,
        layout_id=1,
        car_id=car,
        category=category,
        lap_time_ms=time,
        entry_id=entry,
        driver_name=f"D{entry}",
        round_id=day,
        round_number=day,
        date=datetime(2026, 10, day, tzinfo=UTC),
        timestamp_ms=lap_id,
        ineligible_reason=reason,
    )


def kinds(history):
    return [(item.lap.lap_id, item.kind) for item in history]


def test_each_faster_lap_is_a_new_record():
    history = board([lap(1, 190_000, 1, 1), lap(2, 191_000, 2, 1), lap(3, 189_000, 2, 2)])
    assert kinds(history) == [(1, "record"), (3, "record")]


def test_equal_time_gives_a_shared_record():
    result = boards([lap(1, 189_000, 1, 1), lap(2, 189_000, 2, 2)])[0]
    assert result.record_ms == 189_000
    assert [h.driver_name for h in result.holders] == ["D1", "D2"]


def test_same_driver_with_the_same_time_counts_once():
    result = boards([lap(1, 189_000, 1, 1), lap(2, 189_000, 1, 2)])[0]
    assert len(result.holders) == 1


def test_ineligible_lap_is_not_the_record_but_stays_in_the_history():
    result = boards([lap(1, 190_000, 1, 1), lap(2, 185_000, 2, 2, reason="dsq")])[0]
    assert result.record_ms == 190_000
    assert kinds(result.history) == [(1, "record"), (2, "removed")]


def test_correction_of_the_current_record_gives_the_next_eligible_lap():
    laps = [lap(1, 190_000, 1, 1), lap(2, 189_500, 3, 1), lap(3, 188_000, 2, 2)]
    assert boards(laps)[0].record_ms == 188_000
    corrected = [*laps[:2], lap(3, 188_000, 2, 2, reason="invalid")]
    result = boards(corrected)[0]
    assert result.record_ms == 189_500
    assert result.holders[0].driver_name == "D3"
    assert "removed" in [h.kind for h in result.history]


def test_categories_and_cars_have_separate_boards():
    result = boards(
        [
            lap(1, 189_000, 1, 1, category="qualifying"),
            lap(2, 190_000, 1, 1, category="race"),
            lap(3, 180_000, 2, 1, car=2),
        ]
    )
    assert len(result) == 3
