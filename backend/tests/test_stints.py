from apps.imports.lap_analysis import LapRow
from apps.imports.stints import split_stints


def lap(number, time_ms, tyre="M", pit=None, cuts=0):
    return LapRow(lap_number=number, time_ms=time_ms, sectors_ms=[], cuts=cuts, tyre=tyre, pit=pit)


def test_a_pit_entry_and_a_tyre_change_start_a_new_stint():
    stints = split_stints(
        [
            lap(1, 100_000),
            lap(2, 90_000),
            lap(3, 95_000, pit="in"),  # The pit entry lap ends the first stint.
            lap(4, 120_000, tyre="S", pit="out"),
            lap(5, 88_000, tyre="S"),
            lap(6, 87_000, tyre="S", cuts=1),
            lap(7, 89_000, tyre="H"),  # A new tyre without pit data is a new stint too.
        ]
    )
    assert [(s.number, s.first_lap, s.last_lap, s.laps, s.tyre) for s in stints] == [
        (1, 1, 3, 3, "M"),
        (2, 4, 6, 3, "S"),
        (3, 7, 7, 1, "H"),
    ]
    assert (stints[0].best_ms, stints[0].average_ms, stints[0].ends_in_pit) == (
        90_000,
        95_000,
        True,
    )
    # The cut lap does not count, and the pit exit lap is not in the average.
    assert (stints[1].best_ms, stints[1].average_ms) == (88_000, 88_000)


def test_a_race_on_one_tyre_has_one_stint_and_no_laps_gives_none():
    assert len(split_stints([lap(n, 90_000) for n in range(1, 11)])) == 1
    assert split_stints([]) == []
