"""Lap tables: marks, averages, the theoretical lap, and pit laps from the real race night."""

import pytest
from django.core.management import call_command

from apps.competition.models import Round
from apps.imports.lap_analysis import LapRow, analyze


def row(number, time, sectors, **extra):
    return LapRow(number, time, sectors, **extra)


def test_marks_personal_and_session_bests():
    drivers = {
        "a": [row(1, 100, [30, 40, 30]), row(2, 95, [31, 34, 30])],
        "b": [row(1, 97, [29, 38, 30]), row(2, 99, [32, 37, 30], cuts=1)],
    }
    a, b = analyze(drivers, race=False)
    assert [lap.time_mark for lap in a.laps] == [None, "session"]
    assert [lap.time_mark for lap in b.laps] == ["personal", None]
    # Sector 1: b has the session best (29). Sector 2: a has 34. The cut lap of b gives nothing.
    assert b.laps[0].sector_marks == ["session", "personal", "session"]
    assert a.laps[1].sector_marks == [None, "session", "session"]
    assert b.laps[1].sector_marks == [None, None, None]


def test_averages_show_counts_and_exclusions():
    rows = [
        row(1, 120, []),
        row(2, 100, []),
        row(3, 130, [], pit="in"),
        row(4, 125, [], pit="out"),
        row(5, 102, [], invalid_reason="cut"),
        row(6, 104, []),
    ]
    (laps,) = analyze({"a": rows}, race=True)
    assert (laps.average.ms, laps.average.laps, laps.average.excluded) == (
        round((120 + 100 + 130 + 125 + 104) / 5),
        5,
        {"invalid": 1},
    )
    assert laps.clean_average.ms == 102
    assert laps.clean_average.laps == 2
    assert laps.clean_average.excluded == {"invalid": 1, "pit_in": 1, "pit_out": 1, "first_lap": 1}


def test_theoretical_lap_needs_every_sector():
    (full,) = analyze({"a": [row(1, 100, [30, 40, 30]), row(2, 99, [32, 36, 31])]}, race=False)
    assert full.theoretical_ms == 30 + 36 + 30
    (missing,) = analyze({"a": [row(1, 100, [])]}, race=False)
    assert missing.theoretical_ms is None


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def test_race_laps_of_the_real_night(api, night):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/laps").json()
    assert data["sessions"] == ["race", "qualifying"]
    assert data["has_sectors"] is True and data["has_pit_data"] is True
    first = data["drivers"][0]
    assert first["driver_name"] == "Driver 01"
    assert first["best_lap_ms"] == 189296
    best = next(lap for lap in first["laps"] if lap["lap_number"] == first["best_lap_number"])
    assert best["time_mark"] == "session"
    pits = {
        d["driver_name"]: [lap["pit"] for lap in d["laps"] if lap["pit"]] for d in data["drivers"]
    }
    # Lap 3 has a pit exit and a new entry (a teleport to the pits), so it counts as "in".
    assert pits["Driver 06"] == ["in", "in", "in", "out"]


def test_qualifying_marks_the_invalid_lap(api, night):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/laps?session=qualifying").json()
    laps = [lap for d in data["drivers"] for lap in d["laps"] if lap["lap_number"]]
    invalid = [lap for lap in laps if lap["time_ms"] == 336531]
    assert invalid[0]["valid"] is False
    assert "first_lap" not in data["clean_rules"]


def test_other_championship_cannot_see_laps(api, night, make_user):
    _, round_ = night
    assert api(make_user("stranger")).get(f"/rounds/{round_.id}/laps").status_code == 404
