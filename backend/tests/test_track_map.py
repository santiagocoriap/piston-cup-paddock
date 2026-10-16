"""The track map of the telemetry tool: the fastest full lap of the collector positions."""

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round
from apps.telemetry.track_map import track_map

START = datetime(2026, 10, 11, 19, 30, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


def lap(seconds: int, z: float) -> list[list[float]]:
    """One lap in 100 samples. z is the side of the road: 0 on the track, 9 in the pit lane."""
    step = seconds * 1000 // 100
    return [[i * step, float(i), z, i / 100] for i in range(100)]


def test_the_map_is_the_fastest_full_lap(api, champ_admin, championship, season, layout):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout, scheduled_at=START)
    token, _ = create_token(championship, "AC", champ_admin)
    slow_pit_lap = lap(120, 9.0)
    fast_lap = [[t + 121_000, x, z, s] for t, x, z, s in lap(90, 0.0)]
    CollectorEvent.objects.create(
        token=token,
        run_id="run",
        seq=1,
        kind="positions",
        occurred_at=START,
        data={"cars": {"7656119000000001": slow_pit_lap + fast_lap}},
    )
    points = track_map(round_)
    assert len(points) == 100
    assert {z for _, _, z in points} == {0.0}
    data = api(champ_admin).get(f"/rounds/{round_.id}/track-map").json()
    assert data["spline"][:2] == [0.0, 0.01] and len(data["x"]) == 100


def test_no_full_lap_gives_no_map(champ_admin, championship, season, layout):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout, scheduled_at=START)
    token, _ = create_token(championship, "AC", champ_admin)
    half = [[i * 100, float(i), 0.0, i / 200] for i in range(100)]
    CollectorEvent.objects.create(
        token=token,
        run_id="run",
        seq=1,
        kind="positions",
        occurred_at=START,
        data={"cars": {"a": half}},
    )
    assert track_map(round_) == []
