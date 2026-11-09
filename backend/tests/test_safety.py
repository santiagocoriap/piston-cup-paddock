"""Safety rating, rules safety-2 in docs/LEAGUE_RULES.md."""

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


def test_fewer_points_than_the_field_go_up_and_more_go_down():
    clean = rate([RoundInput(1, "R1", 20, True, field_points=40, field_laps=100)])
    assert clean.history[0].change == 0.40
    assert clean.rating == 2.90
    contacts = [("car", 70, "contact")] * 10  # 20 points in 20 laps: 1 a lap, the field 0.4.
    bad = rate([RoundInput(1, "R1", 20, True, contacts, field_points=40, field_laps=100)])
    assert bad.rating == 2.10
    assert bad.history[0].explanation[0] == "contact"
    assert bad.history[0].per_100_laps == 100.0
    assert bad.history[0].field_per_100_laps == 40.0
    walls = [("env", 50, "w")] * 4
    same = rate([RoundInput(1, "R1", 10, True, walls, field_points=40, field_laps=100)])
    assert same.rating == 2.50  # The rate of the field: no change.


def test_a_short_round_changes_less_and_zero_is_hard_to_reach():
    short = rate([RoundInput(1, "R1", 5, True, field_points=10, field_laps=50)])
    assert short.history[0].change == 0.10
    worst = [RoundInput(n, "R", 20, True, [("car", 150, "x")] * 10, 10, 100) for n in range(10)]
    result = rate(worst)
    assert 0 < result.rating < 0.6  # Ten very bad races in a row.
    assert [c.change for c in result.history][:2] == [-0.40, -0.34]


def test_a_clean_field_gives_a_gain_to_the_clean_drivers():
    assert rate([RoundInput(1, "R1", 20, True)]).rating == 2.90


def test_missing_data_is_unknown_not_clean():
    result = rate([RoundInput(1, "R1", 40, False)])
    assert result.status == "unknown"
    assert result.rating == 2.50
    assert result.history[0].status == "unknown"
    assert result.laps == 0


def test_new_driver_is_provisional_and_rating_stays_in_range():
    result = rate([RoundInput(1, "R1", 10, True, [("car", 150, "x")] * 20, 80, 100)])
    assert result.status == "provisional"
    assert 0 < result.rating < 2.50


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


def test_season_ratings_count_every_start(api, night):
    admin, round_ = night
    unknown = api(admin).get(f"/seasons/{round_.season.id}/safety").json()
    assert {d["status"] for d in unknown["drivers"]} == {"unknown"}

    add_events(admin, round_)
    data = api(admin).get(f"/seasons/{round_.season.id}/safety").json()
    assert data["rules_version"] == "safety-2"
    by_name = {d["driver_name"]: d for d in data["drivers"]}
    winner = by_name["Driver 01"]
    # One car contact, and the wall in the start before the restart: a crash still counts.
    assert winner["points"] == 3
    assert winner["laps"] == 14  # 10 race laps and 4 qualifying laps.
    assert winner["rating"] < 2.50  # More points per lap than the field.
    assert winner["status"] == "provisional"
    assert any("Driver 01 + Driver 03" in line for line in winner["history"][0]["explanation"])
    assert by_name["Driver 06"]["points"] == 0
    assert by_name["Driver 06"]["rating"] > 2.50
