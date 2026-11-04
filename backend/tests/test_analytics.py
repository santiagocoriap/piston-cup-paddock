"""The data analysis pages: the statistics, and the answers with the real race night."""

import math

import pytest
from django.core.management import call_command

from apps.analytics import metrics, racecraft
from apps.catalog.track_line import circuit_type, corner_count
from apps.competition.models import Round


def test_spread_needs_enough_laps_and_finds_outliers():
    assert metrics.spread([]).count == 0
    small = metrics.spread([100, 102])
    assert (small.mean, small.median, small.stdev, small.q1) == (101, 101, None, None)
    values = [100, 101, 102, 103, 104, 105, 106, 200]
    spread = metrics.spread(values)
    assert spread.median == 103.5
    assert spread.outliers == (200,)
    assert spread.high == 106
    assert spread.mad == 2.0
    # The trimmed mean leaves out no lap of 8 (10 % of 8 is below one lap).
    assert spread.trimmed == spread.mean


def test_trimmed_mean_leaves_out_both_ends():
    values = [10, 100, 100, 100, 100, 100, 100, 100, 100, 1000]
    assert metrics.trimmed_mean(values) == 100


def test_lap_order_with_a_lead_change_and_a_lapped_driver():
    order = metrics.lap_order({"a": [100, 100, 100], "b": [99, 102, 100], "c": [150, 150]})
    assert [lap.position for lap in order["a"]] == [2, 1, 1]
    assert [lap.position for lap in order["b"]] == [1, 2, 2]
    assert [lap.gap_to_leader_ms for lap in order["a"]] == [1, 0, 0]
    assert [lap.gap_to_leader_ms for lap in order["b"]] == [0, 1, 1]
    # c has no lap 3: only the cars that completed the lap count on it.
    assert len(order["c"]) == 2
    assert order["c"][1].ahead_ms == 99
    assert order["a"][0].ahead_ms == 1
    assert order["b"][0].ahead_ms is None


def test_battle_share_counts_each_lap_one_time():
    laps = [
        metrics.LapOrder(1, 0, None, 500),
        metrics.LapOrder(2, 900, 900, 400),
        metrics.LapOrder(2, 3000, 3000, 5000),
    ]
    assert metrics.battle_share(laps) == {"attacking": 1, "defending": 1, "clean_air": 1}


def test_elo_gives_points_to_the_winner_and_keeps_the_sum():
    history = metrics.elo([[("a", 1), ("b", 2)], [("a", 1), ("b", 2), ("c", 3)], [("a", 1)]])
    assert history["a"][0] > 1500 > history["b"][0]
    assert len(history["a"]) == 2  # A race with one driver gives no rating.
    assert len(history["c"]) == 1
    total = history["a"][-1] + history["b"][-1] + history["c"][-1]
    assert abs(total - 4500) < 1


def test_scale_gives_100_to_the_best():
    assert metrics.scale({"a": 1.0, "b": 2.0, "c": None}, lower_is_better=True) == {
        "a": 100,
        "b": 0,
        "c": None,
    }
    assert metrics.scale({"a": 1.0}, lower_is_better=True) == {"a": None}
    assert metrics.scale({"a": 3.0, "b": 3.0}, lower_is_better=False) == {"a": 50, "b": 50}


def test_predict_gives_the_title_to_a_driver_who_cannot_lose():
    odds = metrics.predict({"a": 100, "b": 0}, {"a": [25, 25], "b": [10, 18]}, 2, runs=200, seed=1)
    assert odds["a"].win_pct == 100
    assert odds["b"].rank_odds == [0, 100]
    assert odds["a"].expected_rank == 1
    close = metrics.predict({"a": 10, "b": 10}, {"a": [25, 0], "b": [25, 0]}, 3, runs=500, seed=1)
    assert 30 < close["a"].win_pct < 70
    assert sum(close["a"].rank_odds) == 100


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def test_race_analysis_of_the_real_night(api, night):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/analysis").json()
    assert data["session"] == "race"
    assert data["has_sectors"] is True
    drivers = data["drivers"]
    assert len(drivers) > 2
    first = drivers[0]
    assert first["spread"]["count"] == sum(1 for lap in first["laps"] if lap["clean"])
    # On each lap, the positions are 1, 2, 3... with no hole.
    lap_two = sorted(d["laps"][1]["position"] for d in drivers if len(d["laps"]) > 1)
    assert lap_two == list(range(1, len(lap_two) + 1))
    leader = next(d for d in drivers if d["laps"][0]["position"] == 1)
    assert leader["laps"][0]["gap_to_leader_ms"] == 0
    assert any(d["grid"] for d in drivers)
    assert all(d["battle"] is not None for d in drivers)


def test_qualifying_analysis_has_no_order(api, night):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/analysis?session=qualifying").json()
    assert data["session"] == "qualifying"
    assert all(lap["position"] is None for d in data["drivers"] for lap in d["laps"])
    assert all(d["battle"] is None and d["grid"] is None for d in data["drivers"])


def test_season_analysis_of_the_real_night(api, night):
    admin, round_ = night
    data = api(admin).get(f"/seasons/{round_.season_id}/analysis").json()
    assert data["points_by_position"]
    assert [r["number"] for r in data["rounds"]] == [round_.number]
    assert data["rounds"][0]["has_result"] is True
    first = data["drivers"][0]
    cell = first["cells"][0]
    assert cell["total_points"] == first["points"]
    assert cell["rank"] == 1 and cell["gap_to_leader"] == 0
    assert set(first["scores"]) == {
        "pace",
        "consistency",
        "qualifying",
        "results",
        "racecraft",
        "reliability",
    }
    best = [c["pace_pct"] for d in data["drivers"] for c in d["cells"] if c["pace_pct"] is not None]
    assert min(best) == 0
    assert first["can_win"] is True


def test_driver_analysis_lists_the_seasons_of_the_driver(api, night):
    admin, round_ = night
    season = api(admin).get(f"/seasons/{round_.season_id}/analysis").json()
    driver_id = season["drivers"][0]["driver_id"]
    data = api(admin).get(f"/drivers/{driver_id}/analysis").json()
    assert [s["season_id"] for s in data] == [round_.season_id]


def test_another_championship_cannot_see_the_analysis(api, night, make_user):
    _, round_ = night
    stranger = api(make_user("stranger"))
    assert stranger.get(f"/rounds/{round_.id}/analysis").status_code == 404
    assert stranger.get(f"/seasons/{round_.season_id}/analysis").status_code == 404


def _track(rate, seconds=120, start=0.0, stop_at=None):
    """A car at a steady speed: the samples for progress_track."""
    samples = []
    place = start
    for second in range(seconds):
        if stop_at is None or second < stop_at:
            place += rate
        samples.append((float(second), place * 100, 0.0, place % 1))
    return racecraft.progress_track(samples)


def test_a_faster_car_overtakes_and_the_battle_counts():
    found = racecraft.analyze({"fast": _track(0.011, start=0.0), "slow": _track(0.01, start=0.05)})
    assert [(o.attacker, o.defender) for o in found.overtakes] == [("fast", "slow")]
    assert found.overtakes[0].lap == 1
    assert found.battles[0].a == "fast" and found.battles[0].passed is True


def test_a_car_that_stopped_is_not_overtaken():
    found = racecraft.analyze(
        {"a": _track(0.01, start=0.0), "b": _track(0.01, start=0.2, stop_at=30)}
    )
    assert found.overtakes == []


def test_a_lapped_car_does_not_count():
    found = racecraft.analyze({"a": _track(0.0105, start=1.0), "b": _track(0.01, start=0.0)})
    assert found.overtakes == []


def test_a_side_by_side_moment_is_not_an_overtake():
    a = _track(0.01)
    b = {second: ((a[second][0] + (0.001 if 50 <= second < 53 else -0.001)), 0, 0) for second in a}
    assert racecraft.analyze({"a": a, "b": b}).overtakes == []


def test_trend_needs_enough_points():
    assert metrics.trend([(1, 1), (2, 2)]) is None
    slope, start, error = metrics.trend([(1, 2), (2, 4), (3, 6), (4, 8)])
    assert (round(slope, 3), round(start, 3), round(error, 3)) == (2, 0, 0)


def test_the_circuit_type_comes_from_the_corners():
    straight = {
        "length_m": 1000,
        "spline": [i / 99 for i in range(100)],
        "x": list(range(100)),
        "z": [0] * 100,
    }
    assert circuit_type(straight) == ("high_speed", 0)
    angle = [i * 2 * math.pi / 200 for i in range(200)]
    circle = {
        "length_m": 628,
        "spline": [i / 199 for i in range(200)],
        "x": [100 * math.cos(a) for a in angle],
        "z": [100 * math.sin(a) for a in angle],
    }
    assert corner_count(circle) == 1


def test_a_car_on_the_grid_is_on_lap_1_after_the_line():
    samples = [(0.0, 0, 0, 0.99), (1.0, 0, 0, 0.995), (2.0, 0, 0, 0.002), (3.0, 0, 0, 0.01)]
    track = racecraft.progress_track(samples)
    assert round(track[0][0], 2) == -0.01
    assert round(track[3][0], 2) == 0.01
