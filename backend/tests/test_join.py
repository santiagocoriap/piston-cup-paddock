"""A driver joins a season: at once with free join, or by a request that an admin decides."""

import pytest

from apps.community.models import Notification
from apps.competition.models import ChampionshipMember, JoinRequest, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def racer(make_user):
    user = make_user("newbie")
    DriverProfile.objects.create(display_name="Newbie", user=user)
    return user


def join(api, user, season, car, number=11, **extra):
    return api(user).post(
        f"/seasons/{season.id}/join", {"car_id": car.id, "number": number, **extra}
    )


def test_the_options_list_the_seasons_with_their_state(api, racer, season, car):
    options = api(racer).get("/join/seasons").json()
    assert options["has_profile"] is True
    assert options["seasons"][0]["season_id"] == season.id
    assert options["seasons"][0]["free_join"] is False and options["seasons"][0]["mine"] is None
    join(api, racer, season, car)
    assert api(racer).get("/join/seasons").json()["seasons"][0]["mine"] == "pending"


def test_an_account_without_a_driver_profile_has_nothing_to_join(api, make_user, season, car):
    stranger = make_user("nobody")
    assert api(stranger).get("/join/seasons").json() == {"has_profile": False, "seasons": []}
    assert join(api, stranger, season, car).status_code == 422


def test_free_join_enters_the_season_at_once(api, racer, season, car):
    season.free_join = True
    season.save()
    response = join(api, racer, season, car, team="Piston")
    assert response.status_code == 201 and response.json()["status"] == "joined"
    entry = SeasonEntry.objects.get(season=season)
    assert (entry.driver.user, entry.number, entry.team) == (racer, 11, "Piston")
    assert ChampionshipMember.objects.filter(
        championship=season.championship, user=racer, role="driver"
    ).exists()
    assert join(api, racer, season, car, number=12).status_code == 409  # already entered


def test_free_join_refuses_a_taken_number(api, racer, season, car, driver_user):
    season.free_join = True
    season.save()
    SeasonEntry.objects.create(
        season=season, driver=DriverProfile.objects.create(display_name="Other"), car=car, number=11
    )
    assert join(api, racer, season, car).status_code == 409


def test_without_free_join_the_driver_sends_a_request_and_the_admins_hear_of_it(
    api, racer, season, car, champ_admin, league_admin
):
    response = join(api, racer, season, car, note="I race at night")
    assert response.status_code == 201 and response.json()["status"] == "requested"
    assert not SeasonEntry.objects.filter(season=season).exists()
    assert join(api, racer, season, car).status_code == 409  # one pending request
    assert set(
        Notification.objects.filter(kind="join.requested").values_list("user_id", flat=True)
    ) == {
        champ_admin.id,
        league_admin.id,
    }


def test_an_admin_approves_and_the_driver_is_entered(api, racer, season, car, champ_admin):
    join(api, racer, season, car)
    request = JoinRequest.objects.get()
    listed = api(champ_admin).get(f"/seasons/{season.id}/join-requests").json()
    assert [(r["driver_name"], r["number"]) for r in listed] == [("Newbie", 11)]
    response = api(champ_admin).post(f"/join-requests/{request.id}/approve", {})
    assert response.status_code == 200, response.content
    assert SeasonEntry.objects.get(season=season).driver.user == racer
    request.refresh_from_db()
    assert request.status == "approved" and request.decided_by == champ_admin
    assert Notification.objects.filter(user=racer, kind="join.approved").exists()
    assert api(champ_admin).post(f"/join-requests/{request.id}/approve", {}).status_code == 409


def test_approving_can_change_a_taken_number(api, racer, season, car, champ_admin):
    join(api, racer, season, car, number=5)
    SeasonEntry.objects.create(
        season=season, driver=DriverProfile.objects.create(display_name="Other"), car=car, number=5
    )
    request = JoinRequest.objects.get()
    assert api(champ_admin).post(f"/join-requests/{request.id}/approve", {}).status_code == 409
    assert (
        api(champ_admin).post(f"/join-requests/{request.id}/approve", {"number": 6}).status_code
        == 200
    )


def test_an_admin_declines_and_the_driver_can_ask_again(api, racer, season, car, champ_admin):
    join(api, racer, season, car)
    request = JoinRequest.objects.get()
    assert api(champ_admin).post(f"/join-requests/{request.id}/decline").status_code == 200
    assert not SeasonEntry.objects.exists()
    assert Notification.objects.filter(user=racer, kind="join.declined").exists()
    assert api(racer).get("/join/seasons").json()["seasons"][0]["mine"] == "declined"
    assert join(api, racer, season, car, number=12).status_code == 201


def test_only_an_admin_decides(api, racer, season, car, make_user):
    join(api, racer, season, car)
    request = JoinRequest.objects.get()
    for user in (racer, make_user("other")):
        assert api(user).post(f"/join-requests/{request.id}/approve", {}).status_code in (403, 404)
        assert api(user).post(f"/join-requests/{request.id}/decline").status_code in (403, 404)
    assert api(racer).get(f"/seasons/{season.id}/join-requests").status_code in (403, 404)


def test_the_admin_switches_free_join_in_the_season_settings(api, champ_admin, season):
    response = api(champ_admin).client.patch(
        f"/api/seasons/{season.id}/settings", {"free_join": True}, content_type="application/json"
    )
    assert response.status_code == 200 and response.json()["free_join"] is True
