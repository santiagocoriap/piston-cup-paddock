"""Race engineer: time lost in each corner, and the measured reasons, against a reference."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.reports import services as reports
from apps.telemetry import coach
from apps.telemetry.engineer import analyze, corners, to_lap
from apps.telemetry.models import EngineerNote

from .telemetry_laps import save_lap

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
LENGTH_M = 5000


def lap(brake_at=0.30, apex_kmh=100.0, throttle_at=0.345, coast=0.0):
    """A lap with one corner at 0.34. Full throttle at 250 km/h, then (after an optional coast)
    full brakes down to the apex speed, then full throttle from throttle_at."""
    pos, speed, t_ms, gas, brake, gear = [], [], [], [], [], []
    p, t = 0.0, 0.0
    while p <= 1.0:
        if p < brake_at - coast:
            v, g, b = 250.0, 1.0, 0.0
        elif p < brake_at:
            v, g, b = 250.0, 0.0, 0.0
        elif p < 0.34:
            v, g, b = 250 - (250 - apex_kmh) * (p - brake_at) / (0.34 - brake_at), 0.0, 1.0
        elif p < throttle_at:
            v, g, b = apex_kmh, 0.3, 0.0
        else:
            v, g, b = min(250.0, apex_kmh + (p - throttle_at) * 3000), 1.0, 0.0
        pos.append(round(p, 5))
        speed.append(round(v, 1))
        t_ms.append(round(t))
        gas.append(g)
        brake.append(b)
        gear.append(2.0 if v < 150 else 5.0)
        p += v / 3.6 * 0.05 / LENGTH_M  # 20 samples per second.
        t += 50
    return {"pos": pos, "speed_kmh": speed, "t_ms": t_ms, "gas": gas, "brake": brake, "gear": gear}


def kinds(result, number=1):
    corner = next(c for c in result.corners if c.number == number)
    return {cause.kind: cause for cause in corner.causes}


def test_one_corner_and_the_losses_add_up_to_the_lap_gap():
    reference, slow = to_lap(1, lap()), to_lap(2, lap(brake_at=0.29))
    assert len(corners(reference)) == 1
    result = analyze(slow, reference, [slow], LENGTH_M)
    total = sum(c.loss_s for c in result.corners if c.loss_s is not None)
    assert total == pytest.approx(slow.time[-1] - reference.time[-1], abs=0.01)
    assert result.corners[0].loss_s > 0.04


def test_early_braking_is_a_cause_with_the_meters():
    reference, slow = to_lap(1, lap()), to_lap(2, lap(brake_at=0.29))
    cause = kinds(analyze(slow, reference, [slow], LENGTH_M))["brake_early"]
    assert cause.difference == pytest.approx(-50, abs=10)  # 1 % of 5000 m.


def test_slow_apex_late_throttle_and_coasting():
    reference = to_lap(1, lap())
    slow = to_lap(2, lap(apex_kmh=90, throttle_at=0.36, coast=0.004))
    found = kinds(analyze(slow, reference, [slow], LENGTH_M))
    assert found["min_speed"].difference == pytest.approx(-10, abs=1)
    assert found["throttle_late"].difference == pytest.approx(75, abs=15)
    assert found["coasting"].difference >= 10
    assert "exit_speed" in found


def test_a_faster_corner_has_no_cause():
    reference, fast = to_lap(1, lap(brake_at=0.29)), to_lap(2, lap())
    corner = analyze(fast, reference, [fast], LENGTH_M).corners[0]
    assert corner.loss_s < 0 and corner.causes == []


def test_own_best_corners_and_the_ideal_lap():
    laps = [to_lap(1, lap()), to_lap(2, lap(brake_at=0.29)), to_lap(3, lap(apex_kmh=90))]
    result = analyze(laps[1], None, laps, LENGTH_M)
    assert result.corners[0].reference_key == 1
    assert "brake_early" in kinds(result)
    assert result.ideal_s == pytest.approx(laps[0].time[-1], abs=0.05)


def test_spread_over_three_laps():
    laps = [to_lap(n, lap(apex_kmh=v)) for n, v in ((1, 100), (2, 80), (3, 60))]
    spread = analyze(laps[0], None, laps, LENGTH_M).spread
    assert spread and spread[0].min_kmh > 10


def test_a_lap_from_the_grid_starts_at_the_line():
    channels = lap()
    waiting = {key: [values[0]] * 100 + values for key, values in channels.items()}
    waiting["pos"] = [0.998] * 100 + channels["pos"]
    waiting["t_ms"] = [0] * 100 + [t + 5000 for t in channels["t_ms"]]
    standing = to_lap(1, waiting)
    assert standing.time[0] == pytest.approx(0, abs=0.06)
    assert standing.time[-1] == pytest.approx(to_lap(2, channels).time[-1], abs=0.1)


@pytest.fixture
def setup(api, make_user, championship, season, car, layout, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    layout.length_m = LENGTH_M
    layout.save()
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


def test_the_fastest_lap_of_another_driver_is_the_reference(api, setup):
    users, round_ = setup
    data = api(users["slow"]).get(f"/rounds/{round_.id}/engineer").json()
    assert data["reference"]["driver_name"] == "Fast"
    assert data["lap"]["lap_number"] == 1  # The best lap of the driver.
    assert len(data["laps"]) == 3
    assert data["has_pedals"] is True
    assert data["corners"][0]["causes"][0]["kind"] == "brake_early"
    assert [o["driver_name"] for o in data["reference_options"]] == ["Fast"]


def test_the_driver_can_compare_with_the_own_best_corners(api, setup):
    users, round_ = setup
    client = api(users["slow"])
    laps = client.get(f"/rounds/{round_.id}/engineer").json()["laps"]
    third = next(item["id"] for item in laps if item["lap_number"] == 3)
    data = client.get(f"/rounds/{round_.id}/engineer?reference=own&lap={third}").json()
    assert data["reference"] is None
    assert data["lap"]["lap_number"] == 3
    assert data["ideal_s"] is not None


def test_only_an_admin_can_coach_another_driver(api, setup, champ_admin):
    users, round_ = setup
    slow = users["slow"].driver_profile
    answer = api(users["fast"]).get(f"/rounds/{round_.id}/engineer?driver={slow.id}")
    assert answer.status_code == 403
    data = api(champ_admin).get(f"/rounds/{round_.id}/engineer?driver={slow.id}").json()
    assert data["driver"]["name"] == "Slow"
    assert {d["name"] for d in data["drivers"]} == {"Fast", "Slow"}


class FakeAI:
    def __init__(self):
        self.calls = []

    def validate_environment(self, model):
        return {"keys_in_environment": True, "missing_keys": []}

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content="Curva 1: probá frenar 50 m más tarde.")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_the_ai_note_is_written_once_for_the_same_numbers(api, setup, monkeypatch):
    users, round_ = setup
    fake = FakeAI()
    monkeypatch.setattr(reports, "litellm", fake)
    deferred = []
    monkeypatch.setattr(
        "apps.telemetry.tasks.write_note.defer", lambda **kw: deferred.append(kw["note_id"])
    )
    client = api(users["slow"])
    first = client.post(f"/rounds/{round_.id}/engineer/note", {"session": "race"}).json()
    assert first["status"] == "pending"
    note = coach.write(deferred[0])
    assert note.status == EngineerNote.State.READY
    assert "brake_early" in str(fake.calls[0]["messages"][1]["content"])
    second = client.post(f"/rounds/{round_.id}/engineer/note", {"session": "race"}).json()
    assert second["id"] == first["id"] and len(deferred) == 1
    data = client.get(f"/rounds/{round_.id}/engineer").json()
    assert data["note"]["text"].startswith("Curva 1")


def test_no_ai_key_refuses_the_note(api, setup, settings):
    users, round_ = setup
    settings.AI_DISABLED = True
    answer = api(users["slow"]).post(f"/rounds/{round_.id}/engineer/note", {"session": "race"})
    assert answer.status_code == 422
