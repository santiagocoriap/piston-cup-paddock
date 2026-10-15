"""Driver telemetry: the driver key, the round match, and who sees which channels."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.telemetry.models import TelemetryLap

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def people(make_user, championship, season, car, layout):
    """Owner and teammate share team "Red". Rival is in the same season, team "Blue"."""
    users = {}
    for name, team in (("owner", "Red"), ("mate", "Red"), ("rival", "Blue")):
        user = make_user(name)
        ChampionshipMember.objects.create(
            championship=championship, user=user, role=ChampionshipMember.Role.DRIVER
        )
        driver = DriverProfile.objects.create(display_name=name.title(), user=user)
        SeasonEntry.objects.create(
            season=season, driver=driver, car=car, number=len(users) + 1, team=team
        )
        users[name] = user
    users["outsider"] = make_user("outsider")
    round_ = Round.objects.create(
        season=season,
        number=1,
        track_layout=layout,
        scheduled_at=datetime(2026, 10, 11, 19, 0, tzinfo=TZ),
    )
    return users, round_


def lap_body(**extra):
    return {
        "track": "ks_highlands",
        "car": "acura",
        "session_type": "race",
        "lap_number": 3,
        "lap_time_ms": 189296,
        "recorded_at": "2026-10-11T22:35:00Z",
        "sample_hz": 20,
        "channels": {
            "t_ms": [0, 50, 100],
            "pos": [0.0, 0.01, 0.02],
            "speed_kmh": [200, 210, 220],
            "gas": [1, 1, 0.5],
            "brake": [0, 0, 0.3],
        },
        **extra,
    }


@pytest.fixture
def uploaded(api, people):
    users, round_ = people
    key = api(users["owner"]).post("/me/telemetry/key").json()["key"]
    response = Client().post(
        "/api/telemetry/laps",
        lap_body(),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )
    assert response.status_code == 200
    return users, round_, key, response.json()


def test_lap_finds_the_round_and_comes_in_once(uploaded):
    _, round_, key, first = uploaded
    assert first["round_id"] == round_.id and first["is_new"] is True
    again = Client().post(
        "/api/telemetry/laps",
        lap_body(),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )
    assert again.json()["is_new"] is False
    assert TelemetryLap.objects.count() == 1


def test_owner_sees_everything_and_rival_sees_nothing_by_default(api, uploaded):
    users, round_, _, first = uploaded
    detail = api(users["owner"]).get(f"/telemetry-laps/{first['id']}").json()
    assert detail["access"] == "full" and "gas" in detail["channels"]
    assert api(users["rival"]).get(f"/rounds/{round_.id}/telemetry").json() == []
    assert api(users["rival"]).get(f"/telemetry-laps/{first['id']}").status_code == 404
    assert api(users["outsider"]).get(f"/telemetry-laps/{first['id']}").status_code == 404


def test_teammate_gets_what_the_owner_shares(api, uploaded):
    users, _, _, first = uploaded
    detail = api(users["mate"]).get(f"/telemetry-laps/{first['id']}").json()
    assert detail["access"] == "laps"
    assert set(detail["channels"]) == {"t_ms", "pos", "speed_kmh"}
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "full", "drivers": "laps", "admins": "none"}
    )
    assert "brake" in api(users["mate"]).get(f"/telemetry-laps/{first['id']}").json()["channels"]


def test_other_drivers_get_the_level_that_the_driver_chooses(api, uploaded):
    users, _, _, first = uploaded
    owner = api(users["owner"])
    owner.put("/me/telemetry/sharing", {"teammates": "laps", "drivers": "laps", "admins": "laps"})
    detail = api(users["rival"]).get(f"/telemetry-laps/{first['id']}").json()
    assert detail["access"] == "laps"
    assert "gas" not in detail["channels"] and "brake" not in detail["channels"]
    owner.put("/me/telemetry/sharing", {"teammates": "laps", "drivers": "full", "admins": "laps"})
    detail = api(users["rival"]).get(f"/telemetry-laps/{first['id']}").json()
    assert detail["access"] == "full"
    assert "gas" in detail["channels"] and "brake" in detail["channels"]


def test_admin_access_follows_the_admin_setting(api, champ_admin, uploaded):
    users, _, _, first = uploaded
    admin = api(champ_admin)
    assert admin.get(f"/telemetry-laps/{first['id']}").json()["access"] == "laps"
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "full"}
    )
    assert admin.get(f"/telemetry-laps/{first['id']}").json()["access"] == "full"
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "none"}
    )
    assert admin.get(f"/telemetry-laps/{first['id']}").status_code == 404


def test_bad_key_and_bad_channels_are_refused(api, uploaded):
    _, _, key, _ = uploaded
    bad_key = Client().post(
        "/api/telemetry/laps",
        lap_body(),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer nope",
    )
    assert bad_key.status_code == 401
    body = lap_body(lap_number=4)
    body["channels"]["setup_secret"] = [1, 2, 3]
    response = Client().post(
        "/api/telemetry/laps",
        body,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )
    assert response.json()["detail"] == "unknown_channels"


def test_new_key_stops_the_old_key(api, uploaded):
    users, _, old_key, _ = uploaded
    api(users["owner"]).post("/me/telemetry/key")
    response = Client().get("/api/telemetry/status", HTTP_AUTHORIZATION=f"Bearer {old_key}")
    assert response.status_code == 401


def test_status_for_the_driver(api, uploaded):
    users, _, _, _ = uploaded
    data = api(users["owner"]).get("/me/telemetry").json()
    assert (data["has_key"], data["laps"]) == (True, 1)
    assert data["sharing"] == {"teammates": "laps", "drivers": "none", "admins": "laps"}
