"""The samples of a lap keep only the lap itself (the finish line fix)."""

from apps.telemetry.samples import trim_to_lap


def channels(times):
    return {"t_ms": times, "pos": [round(t / 1000, 3) for t in times]}


def test_a_sample_of_the_next_lap_at_the_end_goes_away():
    clean = trim_to_lap(channels([345, 432, 143808, 143859, 6]), 143902)
    assert clean["t_ms"] == [345, 432, 143808, 143859]
    assert len(clean["pos"]) == 4


def test_a_sample_of_the_lap_before_at_the_start_goes_away():
    clean = trim_to_lap(channels([113859, 54, 102, 105294]), 105337)
    assert clean["t_ms"] == [54, 102, 105294]


def test_a_stale_sample_inside_the_slack_also_goes_away():
    clean = trim_to_lap(channels([100050, 40, 90, 100000]), 100000)
    assert clean["t_ms"] == [40, 90, 100000]


def test_a_clean_lap_stays_as_it_is():
    data = channels([69, 123, 113805])
    assert trim_to_lap(data, 113860) == data
