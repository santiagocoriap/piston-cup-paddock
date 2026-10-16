"""A driver chooses the skin of the car of the entry, and the server push carries it."""

import pytest

from apps.catalog.models import Car, CarSkin
from apps.collectors.server_setup import build
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def skins(car):
    return [CarSkin.objects.create(car=car, key=key, name=key.title()) for key in ("red", "blue")]


@pytest.fixture
def entry(season, car, driver_user):
    profile = DriverProfile.objects.create(display_name="Racer", user=driver_user)
    return SeasonEntry.objects.create(season=season, driver=profile, car=car, number=7)


def put(api, user, entry, skin_id):
    return api(user).put(f"/entries/{entry.id}/skin", {"skin_id": skin_id})


def test_the_driver_chooses_a_skin_of_their_car(api, driver_user, entry, skins):
    listed = api(driver_user).get(f"/entries/{entry.id}/skins").json()
    assert {s["key"] for s in listed} == {"red", "blue"}
    response = put(api, driver_user, entry, skins[0].id)
    assert response.status_code == 200, response.content
    assert response.json()["skin_id"] == skins[0].id and response.json()["mine"] is True
    entry.refresh_from_db()
    assert entry.skin == skins[0]
    season = api(driver_user).get(f"/seasons/{entry.season_id}").json()
    assert season["entries"][0]["skin_name"] == "Red" and season["entries"][0]["mine"] is True


def test_the_driver_can_go_back_to_no_choice(api, driver_user, entry, skins):
    put(api, driver_user, entry, skins[0].id)
    assert put(api, driver_user, entry, None).json()["skin_id"] is None


def test_a_skin_of_another_car_is_refused(api, driver_user, entry):
    other = Car.objects.create(key="bmw", name="BMW")
    stranger = CarSkin.objects.create(car=other, key="white")
    assert put(api, driver_user, entry, stranger.id).status_code == 422


def test_another_driver_cannot_choose_for_this_entry(api, make_user, championship, entry, skins):
    from apps.competition.models import ChampionshipMember

    rival = make_user("rival")
    ChampionshipMember.objects.create(
        championship=championship, user=rival, role=ChampionshipMember.Role.DRIVER
    )
    assert put(api, rival, entry, skins[0].id).status_code == 403
    assert api(rival).get(f"/entries/{entry.id}/skins").status_code == 403


def test_a_manager_can_choose_for_a_driver(api, champ_admin, entry, skins):
    assert put(api, champ_admin, entry, skins[1].id).status_code == 200
    entry.refresh_from_db()
    assert entry.skin == skins[1]


def test_a_deleted_skin_leaves_the_entry_without_a_choice(entry, skins):
    entry.skin = skins[0]
    entry.save()
    skins[0].delete()
    entry.refresh_from_db()
    assert entry.skin is None


def test_the_server_push_carries_the_skin(entry, skins, season, layout):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    assert build(round_, "https://paddock.test")["entries"][0]["skin"] == ""
    entry.skin = skins[1]
    entry.save()
    assert build(round_, "https://paddock.test")["entries"][0]["skin"] == "blue"
