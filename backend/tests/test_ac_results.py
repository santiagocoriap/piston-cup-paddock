"""The parser against the real, sanitized race night in samples/."""

import json
from pathlib import Path

import pytest

from apps.imports.ac_results import ResultFileError, parse, track_key

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"


def load(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def race():
    return parse(load("2026_10_11_20_7_RACE.json"))


def test_track_key_removes_the_csp_prefix():
    assert track_key("csp/3460/../D/../ks_highlands") == "ks_highlands"
    assert track_key("ks_highlands") == "ks_highlands"


def test_race_has_the_five_drivers_with_laps_in_classification_order(race):
    assert race.session_type == "race"
    assert (race.track, race.layout) == ("ks_highlands", "layout_long")
    assert [d.name for d in race.drivers] == [
        "Driver 01",
        "Driver 03",
        "Driver 06",
        "Driver 05",
        "Driver 04",
    ]
    assert [d.laps for d in race.drivers] == [10, 10, 9, 6, 1]


def test_driver_guid_comes_from_the_laps(race):
    car_3 = next(d for d in race.drivers if d.car_id == 3)
    assert car_3.guid == "76561190000000004"
    assert car_3.result_guid == "76561190000000011"


def test_entries_without_laps_are_skipped(race):
    names = {d.name for d in race.drivers}
    assert "Race Control" not in names
    assert "Driver 02" not in names


def test_lap_data_has_sectors_tyres_and_handicaps(race):
    lap = race.laps[0]
    assert len(lap.sectors_ms) == 3
    assert lap.tyre in {"S", "M", "H"}
    assert race.drivers[0].ballast_kg == 8
    assert "sectors" not in race.missing
    assert "conditions" in race.missing


def test_qualifying_file_is_a_qualifying_session():
    assert parse(load("2026_10_11_18_54_QUALIFY.json")).session_type == "qualifying"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ({"hello": 1}, "not_a_result_file"),
        ({"Type": "DRIFT", "Result": [], "Laps": []}, "unknown_session_type"),
    ],
)
def test_bad_files_are_refused(data, code):
    with pytest.raises(ResultFileError) as error:
        parse(data)
    assert error.value.code == code
