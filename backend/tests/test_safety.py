"""Safety rating, rules safety-1 in docs/LEAGUE_RULES.md."""

from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round
from apps.rules.safety import RoundInput, incident_points, rate


def test_points_for_each_kind_and_fast_impacts():
    assert incident_points("env", 60) == 1
    assert incident_points("car", 60) == 2
    assert incident_points("car", 120) == 4
    assert incident_points("env", 100) == 1  # Only faster than 100 counts double.


def test_clean_laps_go_up_and_points_go_down_with_explanation():
    rounds = [
        RoundInput(1, "R1", 30, True),
        RoundInput(2, "R2", 20, True, [("car", 70, "contact")]),
    ]
    result = rate(rounds)
    assert [c.change for c in result.history] == [0.30, 0.10]
    assert result.rating == 3.40
    assert result.history[1].explanation == ["contact"]
    assert (result.status, result.laps, result.points, result.per_100_laps) == (
        "rated",
        50,
        2,
        4.0,
    )


def test_missing_data_is_unknown_not_clean():
    result = rate([RoundInput(1, "R1", 40, False)])
    assert result.status == "unknown"
    assert result.rating == 3.00
    assert result.history[0].status == "unknown"
    assert result.laps == 0


def test_new_driver_is_provisional_and_rating_stays_in_range():
    result = rate([RoundInput(1, "R1", 10, True, [("car", 150, "x")] * 20)])
    assert result.status == "provisional"
    assert result.rating == 0.0


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def add_events(admin, round_):
    token, _ = create_token(round_.season.championship, "AC", admin)
    start = round_.scheduled_at
    d1, d3 = "76561190000000001", "76561190000000003"
    rows = [
        ("session_started", 0, {"type": 3}),
        ("collision_env", 30, {"guid": d1, "speed_kmh": 50}),  # Abandoned start: not counted.
        ("session_started", 60, {"type": 3}),  # The accepted start.
        ("collision_car", 200, {"guid": d1, "speed_kmh": 60, "other": {"guid": d3}}),
        ("collision_car", 200, {"guid": d3, "speed_kmh": 60, "other": {"guid": d1}}),
    ]
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="run",
            seq=seq,
            kind=kind,
            occurred_at=start + timedelta(seconds=seconds),
            data=data,
        )


def test_season_ratings_from_the_accepted_start(api, night):
    admin, round_ = night
    unknown = api(admin).get(f"/seasons/{round_.season.id}/safety").json()
    assert {d["status"] for d in unknown["drivers"]} == {"unknown"}

    add_events(admin, round_)
    data = api(admin).get(f"/seasons/{round_.season.id}/safety").json()
    assert data["rules_version"] == "safety-1"
    by_name = {d["driver_name"]: d for d in data["drivers"]}
    winner = by_name["Driver 01"]
    assert winner["points"] == 2  # One car contact. The wall in the abandoned start is out.
    assert winner["laps"] == 10
    assert winner["rating"] == pytest.approx(3.00 + 0.10 - 0.10)
    assert winner["status"] == "provisional"
    assert "Driver 01 + Driver 03" in winner["history"][0]["explanation"][0]
    assert by_name["Driver 06"]["points"] == 0
    assert by_name["Driver 06"]["rating"] > 3.00
