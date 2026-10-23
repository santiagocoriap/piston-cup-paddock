"""The car classes of a season: a car vote sets them, the voters get an entry, and each car
choice stays inside the classes."""

from datetime import date

import pytest

from apps.catalog.models import Car, CarClass, CarClassMembership
from apps.community.models import Notification
from apps.competition.models import ChampionshipMember, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def classes(db):
    """2 classes: TC with 3 cars, and GT3 with 1 car."""
    tc = CarClass.objects.create(name="TC")
    gt3 = CarClass.objects.create(name="GT3")
    cars = {}
    for key, car_class in [("camry", tc), ("mustang", tc), ("torino", tc), ("gt3_audi", gt3)]:
        cars[key] = Car.objects.create(key=key, name=key.title())
        CarClassMembership.objects.create(
            car_class=car_class, car=cars[key], valid_from=date(2026, 1, 1)
        )
    return tc, gt3, cars


@pytest.fixture
def racers(make_user, championship):
    """3 drivers with an account: they are the voters."""
    users = []
    for name in ["ana", "bruno", "carla"]:
        user = make_user(name)
        ChampionshipMember.objects.create(
            championship=championship, user=user, role=ChampionshipMember.Role.DRIVER
        )
        DriverProfile.objects.create(display_name=name.title(), user=user)
        users.append(user)
    return users


def decide_class(api, admin, season, voters, winner: CarClass, other: CarClass):
    client = api(admin)
    detail = client.post(
        f"/seasons/{season.id}/ballots",
        {"kind": "car_class", "title": "Clase", "method": "single", "slots": 1},
    ).json()
    detail = client.put(f"/ballots/{detail['id']}/options", {"ids": [winner.id, other.id]}).json()
    detail = client.post(f"/ballots/{detail['id']}/open").json()
    option = next(o for o in detail["options"] if o["car_class_id"] == winner.id)
    for voter in voters:
        api(voter).put(f"/ballots/{detail['id']}/vote", {"option_ids": [option["id"]]})
    client.post(f"/ballots/{detail['id']}/close", {})
    return detail


def test_a_class_option_shows_car_pictures_and_the_count(api, champ_admin, season, classes):
    tc, gt3, _ = classes
    client = api(champ_admin)
    detail = client.post(
        f"/seasons/{season.id}/ballots", {"kind": "car_class", "title": "Clase", "method": "single"}
    ).json()
    candidates = client.get(f"/ballots/{detail['id']}/candidates").json()
    by_name = {c["label"]: c for c in candidates}
    assert by_name["TC"]["car_count"] == 3
    assert by_name["GT3"]["car_count"] == 1
    # No car has a picture in this test, so the list is empty but present.
    assert by_name["TC"]["images"] == []


def test_the_vote_sets_the_class_and_enters_the_voters(api, champ_admin, season, classes, racers):
    tc, gt3, cars = classes
    decide_class(api, champ_admin, season, racers, tc, gt3)
    assert list(season.car_classes.all()) == [tc]
    entries = SeasonEntry.objects.filter(season=season).select_related("car")
    assert entries.count() == 3
    assert {e.car.key for e in entries} <= {"camry", "mustang", "torino"}
    assert sorted(e.number for e in entries) == [1, 2, 3]
    assert Notification.objects.filter(kind="entry.auto_created").count() == 3
    detail = api(racers[0]).get(f"/seasons/{season.id}").json()
    assert [c["name"] for c in detail["car_classes"]] == ["TC"]
    assert sorted(detail["car_ids"]) == sorted(cars[k].id for k in ("camry", "mustang", "torino"))


def test_a_driver_changes_the_own_car_inside_the_class(api, champ_admin, season, classes, racers):
    tc, gt3, cars = classes
    decide_class(api, champ_admin, season, racers, tc, gt3)
    entry = SeasonEntry.objects.get(season=season, driver__user=racers[0])
    client = api(racers[0])
    answer = client.put(f"/entries/{entry.id}/car", {"car_id": cars["gt3_audi"].id})
    assert answer.status_code == 422 and answer.json()["detail"] == "car_not_in_class"
    target = cars["torino"] if entry.car.key != "torino" else cars["camry"]
    assert client.put(f"/entries/{entry.id}/car", {"car_id": target.id}).status_code == 200
    entry.refresh_from_db()
    assert entry.car == target
    # Another driver cannot change it.
    assert api(racers[1]).put(f"/entries/{entry.id}/car", {"car_id": target.id}).status_code == 403


def test_an_admin_entry_must_use_a_car_of_the_class(api, champ_admin, season, classes):
    tc, _, cars = classes
    season.car_classes.set([tc])
    driver = DriverProfile.objects.create(display_name="Diego")
    answer = api(champ_admin).post(
        f"/seasons/{season.id}/entries",
        {"driver_id": driver.id, "car_id": cars["gt3_audi"].id, "number": 9},
    )
    assert answer.status_code == 422 and answer.json()["detail"] == "car_not_in_class"


def test_a_season_with_no_class_allows_any_car(api, champ_admin, season, classes):
    _, _, cars = classes
    detail = api(champ_admin).get(f"/seasons/{season.id}").json()
    assert detail["car_ids"] is None and detail["car_classes"] == []
    driver = DriverProfile.objects.create(display_name="Eva")
    answer = api(champ_admin).post(
        f"/seasons/{season.id}/entries",
        {"driver_id": driver.id, "car_id": cars["gt3_audi"].id, "number": 5},
    )
    assert answer.status_code == 201


def test_an_admin_sets_the_classes_by_hand(api, champ_admin, season, classes):
    tc, gt3, _ = classes
    detail = (
        api(champ_admin)
        .put(f"/seasons/{season.id}/car-classes", {"class_ids": [gt3.id, tc.id]})
        .json()
    )
    assert sorted(c["name"] for c in detail["car_classes"]) == ["GT3", "TC"]


def test_an_admin_enters_a_driver_with_no_car_and_the_vote_gives_one(
    api, champ_admin, season, classes, racers
):
    tc, gt3, cars = classes
    profile = DriverProfile.objects.get(user=racers[0])
    answer = api(champ_admin).post(
        f"/seasons/{season.id}/entries", {"driver_id": profile.id, "number": 5}
    )
    assert answer.status_code == 201
    assert (answer.json()["car_id"], answer.json()["car_name"]) == (None, "")
    decide_class(api, champ_admin, season, racers, tc, gt3)
    entry = SeasonEntry.objects.get(season=season, driver=profile)
    assert entry.number == 5
    assert entry.car.key in {"camry", "mustang", "torino"}


def test_a_driver_with_no_car_stays_out_of_the_server_entry_list(season, classes):
    from django.utils import timezone

    from apps.catalog.models import Track, TrackLayout
    from apps.collectors.server_setup import build
    from apps.competition.models import Round

    _, _, cars = classes
    ana = DriverProfile.objects.create(display_name="Ana", steam_guid="76561190000000001")
    bob = DriverProfile.objects.create(display_name="Bob", steam_guid="76561190000000002")
    SeasonEntry.objects.create(season=season, driver=ana, car=cars["camry"], number=1)
    SeasonEntry.objects.create(season=season, driver=bob, number=2)
    track = Track.objects.create(key="ks_vallelunga", name="Vallelunga")
    layout = TrackLayout.objects.create(track=track, key="club", name="Club")
    round_ = Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at=timezone.now()
    )
    content = build(round_, "https://paddock.example.com")
    assert [e["name"] for e in content["entries"]] == ["Ana"]
    assert "no_car:Bob" in content["warnings"]


def test_an_admin_adds_a_voter_to_an_open_vote(api, champ_admin, season, classes, racers):
    tc, gt3, _ = classes
    client = api(champ_admin)
    detail = client.post(
        f"/seasons/{season.id}/ballots", {"kind": "car_class", "title": "Clase", "slots": 1}
    ).json()
    client.put(f"/ballots/{detail['id']}/options", {"ids": [tc.id, gt3.id]})
    detail = client.post(f"/ballots/{detail['id']}/open").json()
    voters = {v["username"] for v in detail["voters"]}
    # A driver who joins the championship after the opening is not a voter yet.
    late = racers[0].__class__.objects.create_user("late")
    ChampionshipMember.objects.create(
        championship=season.championship, user=late, role=ChampionshipMember.Role.DRIVER
    )
    candidates = client.get(f"/ballots/{detail['id']}/voter-candidates").json()
    assert [(c["username"], c["eligible"]) for c in candidates] == [("late", True)]
    assert "late" not in voters
    added = client.post(f"/ballots/{detail['id']}/voters", {"user_ids": [late.id]}).json()
    assert "late" in {v["username"] for v in added["voters"]}
    assert Notification.objects.filter(user=late, kind="ballot.open").exists()
    option = added["options"][0]["id"]
    assert (
        api(late).put(f"/ballots/{detail['id']}/vote", {"option_ids": [option]}).status_code == 200
    )
    again = client.post(f"/ballots/{detail['id']}/voters", {"user_ids": [late.id]})
    assert again.json()["detail"] == "not_a_candidate"
    driver = api(racers[1]).post(f"/ballots/{detail['id']}/voters", {"user_ids": [late.id]})
    assert driver.status_code == 403
