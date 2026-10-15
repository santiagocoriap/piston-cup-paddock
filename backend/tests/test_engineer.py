"""Race engineer: advice only from repeated, measured differences, with evidence."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.telemetry.engineer import Trace, analyze, lap_length_m

from .telemetry_laps import save_lap

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
LENGTH_M = 5000


def lap(brake_at=0.30, apex_kmh=100.0, exit_kmh=None):
    """A lap with one corner. Speed 250, braking from brake_at to the apex at 0.34."""
    exit_kmh = exit_kmh or apex_kmh + 60
    pos, speed, t_ms = [], [], []
    p, t = 0.0, 0.0
    while p <= 1.0:
        if p < brake_at:
            v = 250.0
        elif p < 0.34:
            v = 250 - (250 - apex_kmh) * (p - brake_at) / (0.34 - brake_at)
        elif p < 0.36:
            v = apex_kmh + (exit_kmh - apex_kmh) * (p - 0.34) / 0.02
        else:
            v = min(250.0, exit_kmh + (p - 0.36) * 2000)
        pos.append(round(p, 5))
        speed.append(round(v, 1))
        t_ms.append(round(t))
        step_m = v / 3.6 * 0.05  # 20 samples per second.
        p += step_m / LENGTH_M
        t += 50
    return {"pos": pos, "speed_kmh": speed, "t_ms": t_ms}


def trace(channels):
    return Trace.from_samples(channels["pos"], channels["speed_kmh"])


def test_lap_length_comes_from_speed_and_time():
    reference = lap()
    assert lap_length_m(reference["pos"], reference["t_ms"], reference["speed_kmh"]) == (
        pytest.approx(LENGTH_M, rel=0.02)
    )


def test_repeated_early_braking_gives_advice_with_evidence():
    reference = lap()
    laps = [trace(lap(brake_at=0.29)) for _ in range(3)]
    result = analyze(trace(reference), laps, LENGTH_M)
    assert result.zones == 1
    advice = next(a for a in result.advice if a.kind == "brake_later")
    assert advice.difference == pytest.approx(50, abs=15)  # 1 % of 5000 m.
    assert (advice.laps_showing, advice.laps_total) == (3, 3)
    assert len(advice.lap_values) == 3


def test_one_odd_lap_gives_no_advice():
    reference = lap()
    laps = [trace(lap(brake_at=0.29)), trace(lap()), trace(lap())]
    result = analyze(trace(reference), laps, LENGTH_M)
    assert [a for a in result.advice if a.kind == "brake_later"] == []


def test_slow_apex_and_spread_exits():
    reference = lap(apex_kmh=110)
    laps = [trace(lap(apex_kmh=95, exit_kmh=e)) for e in (130, 150, 170)]
    kinds = {a.kind for a in analyze(trace(reference), laps, LENGTH_M).advice}
    assert {"carry_speed", "consistent_exit"} <= kinds


def test_needs_two_laps():
    assert analyze(trace(lap()), [trace(lap(brake_at=0.29))], LENGTH_M).advice == []


@pytest.fixture
def setup(api, make_user, championship, season, car, layout, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    round_ = Round.objects.create(
        season=season,
        number=1,
        track_layout=layout,
        scheduled_at=datetime(2026, 10, 11, 19, 0, tzinfo=TZ),
    )
    users = {}
    for number, name in ((1, "fast"), (2, "slow")):
        user = make_user(name)
        ChampionshipMember.objects.create(
            championship=championship, user=user, role=ChampionshipMember.Role.DRIVER
        )
        driver = DriverProfile.objects.create(display_name=name.title(), user=user)
        SeasonEntry.objects.create(season=season, driver=driver, car=car, number=number)
        users[name] = user
    # The fast driver shares lap times and speed with other drivers.
    api(users["fast"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "laps", "admins": "laps"}
    )
    uploads = [("fast", 1, lap(), 180000)] + [
        ("slow", n, lap(brake_at=0.29), 181000 + n) for n in (1, 2, 3)
    ]
    for name, number, channels, time_ms in uploads:
        save_lap(
            users[name].driver_profile,
            round_,
            channels,
            car="car",
            lap_number=number,
            lap_time_ms=time_ms,
            recorded_at=datetime.fromisoformat("2026-10-11T22:40:00+00:00"),
        )
    return users, round_


def test_engineer_uses_the_session_best_as_reference(api, setup):
    users, round_ = setup
    data = api(users["slow"]).get(f"/rounds/{round_.id}/engineer").json()
    assert data["reference"]["driver_name"] == "Fast"
    assert data["reference"]["own"] is False
    assert len(data["laps"]) == 3
    assert any(a["kind"] == "brake_later" for a in data["advice"])
    assert data["setup_missing"] == ["setup", "tyre_temperatures", "fuel", "track_conditions"]


def test_reference_without_sharing_is_the_own_best(api, setup):
    users, round_ = setup
    api(users["fast"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "laps"}
    )
    data = api(users["slow"]).get(f"/rounds/{round_.id}/engineer").json()
    assert data["reference"]["own"] is True
    assert len(data["laps"]) == 2
