"""Driver telemetry: who sees which channels."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile

from .telemetry_laps import save_lap

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


CHANNELS = {
    "t_ms": [0, 50, 100],
    "pos": [0.0, 0.01, 0.02],
    "speed_kmh": [200, 210, 220],
    "gas": [1, 1, 0.5],
    "brake": [0, 0, 0.3],
}


@pytest.fixture
def uploaded(people):
    users, round_ = people
    lap = save_lap(users["owner"].driver_profile, round_, CHANNELS)
    return users, round_, None, {"id": lap.id}


def test_the_league_sees_everything_by_default(api, uploaded):
    users, round_, _, first = uploaded
    detail = api(users["owner"]).get(f"/telemetry-laps/{first['id']}").json()
    assert detail["access"] == "full" and "gas" in detail["channels"]
    rival = api(users["rival"])
    assert [lap["access"] for lap in rival.get(f"/rounds/{round_.id}/telemetry").json()] == ["full"]
    assert "brake" in rival.get(f"/telemetry-laps/{first['id']}").json()["channels"]
    # A person outside the championship still sees nothing.
    assert api(users["outsider"]).get(f"/telemetry-laps/{first['id']}").status_code == 404


def test_a_driver_can_hide_the_telemetry_from_rivals(api, uploaded):
    users, round_, _, first = uploaded
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "laps"}
    )
    assert api(users["rival"]).get(f"/rounds/{round_.id}/telemetry").json() == []
    assert api(users["rival"]).get(f"/telemetry-laps/{first['id']}").status_code == 404


def test_teammate_gets_what_the_owner_shares(api, uploaded):
    users, _, _, first = uploaded
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "laps"}
    )
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
    assert admin.get(f"/telemetry-laps/{first['id']}").json()["access"] == "full"
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "laps"}
    )
    assert admin.get(f"/telemetry-laps/{first['id']}").json()["access"] == "laps"
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "full"}
    )
    assert admin.get(f"/telemetry-laps/{first['id']}").json()["access"] == "full"
    api(users["owner"]).put(
        "/me/telemetry/sharing", {"teammates": "laps", "drivers": "none", "admins": "none"}
    )
    assert admin.get(f"/telemetry-laps/{first['id']}").status_code == 404


def test_status_for_the_driver(api, uploaded):
    users, _, _, _ = uploaded
    data = api(users["owner"]).get("/me/telemetry").json()
    assert data["laps"] == 1
    assert data["sharing"] == {"teammates": "full", "drivers": "full", "admins": "full"}
