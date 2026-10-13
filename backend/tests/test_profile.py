"""Driver profile: career level with adjustments, seasons, records, safety, and restarts."""

import pytest
from django.core.management import call_command

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.dashboard.profile import level_for
from apps.identity.models import DriverProfile
from apps.restarts.models import Restart


def test_level_rule():
    assert [level_for(p) for p in (0, 99, 100, 250)] == [1, 1, 2, 3]


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    return admin, round_


def test_profile_of_the_winner(api, night):
    admin, round_ = night
    client = api(admin)
    client.post(f"/rounds/{round_.id}/result/approve")
    driver = DriverProfile.objects.get(display_name="Driver 01")
    restart = Restart.objects.first()
    restart.review_status = Restart.Review.CONFIRMED
    restart.responsibility = Restart.Responsibility.DRIVERS
    restart.save()
    restart.responsible_entries.set([SeasonEntry.objects.get(driver=driver)])

    data = client.get(f"/drivers/{driver.id}/profile").json()
    assert data["career"] == {
        "raw_points": 25,
        "points": 25,
        "level": 1,
        "next_level_points": 100,
        "adjustments": [],
    }
    season = data["seasons"][0]
    assert (season["rank"], season["wins"], season["podiums"], season["starts"]) == (1, 1, 1, 1)
    assert any(r["category"] == "race" for r in data["records"])
    assert data["restarts_caused"][0]["label"] == "2026 R1"
    assert data["safety"][0]["status"] == "unknown"  # No collector events.
    assert data["can_adjust"] is True


def test_adjust_and_reset_keep_the_history(api, night):
    admin, round_ = night
    client = api(admin)
    client.post(f"/rounds/{round_.id}/result/approve")
    driver = DriverProfile.objects.get(display_name="Driver 01")
    url = f"/drivers/{driver.id}/career"
    data = client.post(url, {"kind": "adjust", "points": 100, "reason": "Temporada vieja"}).json()
    assert (data["career"]["points"], data["career"]["level"]) == (125, 2)
    data = client.post(url, {"kind": "reset", "reason": "Empieza de nuevo"}).json()
    assert data["career"]["points"] == 0
    assert data["career"]["raw_points"] == 25  # The race history stays.
    data = client.post(url, {"kind": "adjust", "points": 10, "reason": "Bonus"}).json()
    assert data["career"]["points"] == 10
    assert [a["kind"] for a in data["career"]["adjustments"]] == ["adjust", "reset", "adjust"]


def test_driver_cannot_adjust_and_strangers_cannot_see(api, night, make_user):
    _, round_ = night
    driver = DriverProfile.objects.get(display_name="Driver 01")
    driver_user = make_user("racer")
    ChampionshipMember.objects.create(
        championship=round_.season.championship,
        user=driver_user,
        role=ChampionshipMember.Role.DRIVER,
    )
    stranger = make_user("stranger")
    assert api(stranger).get(f"/drivers/{driver.id}/profile").status_code == 404
    response = api(driver_user).post(
        f"/drivers/{driver.id}/career", {"kind": "reset", "reason": "x"}
    )
    assert response.status_code == 403


def test_standings_link_to_the_driver(api, night):
    admin, round_ = night
    rows = api(admin).get(f"/seasons/{round_.season.id}/standings").json()
    assert rows[0]["driver_id"] == DriverProfile.objects.get(display_name=rows[0]["driver_name"]).id
