"""Car subclasses: a class can hold subclasses (F1 → 80s F1, 2000s F1), and a car class vote can
choose in 2 rounds: first the class, then one of its subclasses."""

from datetime import date

import pytest

from apps.catalog.models import Car, CarClass, CarClassMembership, classes_of
from apps.competition.cars import allowed_cars
from apps.competition.models import SeasonEntry
from apps.voting.models import Ballot

from .test_season_cars import racers  # noqa: F401  (a fixture)


@pytest.fixture
def f1(db):
    """F1 with 2 subclasses, and GT3 with no subclass. Each class has 1 car."""
    f1 = CarClass.objects.create(name="F1")
    eighties = CarClass.objects.create(name="80s F1", parent=f1)
    modern = CarClass.objects.create(name="2000s F1", parent=f1)
    gt3 = CarClass.objects.create(name="GT3")
    for key, car_class in [("mp4", eighties), ("f2004", modern), ("audi", gt3)]:
        car = Car.objects.create(key=key, name=key.upper())
        CarClassMembership.objects.create(car_class=car_class, car=car, valid_from=date(2026, 1, 1))
    return f1, eighties, modern, gt3


def test_a_subclass_belongs_to_one_class_with_no_parent(api, champ_admin, f1):
    parent, eighties, _, gt3 = f1
    client = api(champ_admin)
    made = client.post("/catalog/classes", {"name": "Early F1", "parent_id": parent.id})
    assert made.status_code == 201 and made.json()["parent_id"] == parent.id
    # Only one level: a subclass cannot hold subclasses.
    deep = client.post("/catalog/classes", {"name": "1982", "parent_id": eighties.id})
    assert deep.json()["detail"] == "class_parent_is_subclass"
    # A class with subclasses cannot become a subclass.
    moved = client.patch(f"/catalog/classes/{parent.id}", {"parent_id": gt3.id})
    assert moved.json()["detail"] == "class_has_subclasses"
    # A subclass can leave its parent.
    freed = client.patch(f"/catalog/classes/{eighties.id}", {"parent_id": None}).json()
    assert freed["parent_id"] is None and freed["name"] == "80s F1"


def test_a_class_holds_the_cars_of_its_subclasses(season, f1):
    parent, eighties, _, _ = f1
    season.car_classes.set([parent])
    assert sorted(allowed_cars(season).values_list("key", flat=True)) == ["f2004", "mp4"]
    mp4 = Car.objects.get(key="mp4")
    assert classes_of(mp4.id, date(2026, 6, 1)) == [eighties.id, parent.id]


def class_ballot(client, season, ids, **settings):
    data = {"kind": "car_class", "title": "Clase", "method": "single", "slots": 1, **settings}
    detail = client.post(f"/seasons/{season.id}/ballots", data).json()
    client.put(f"/ballots/{detail['id']}/options", {"ids": ids})
    return client.post(f"/ballots/{detail['id']}/open").json()


def vote_and_close(api, admin, detail, label, voters):
    option = next(o for o in detail["options"] if o["label"] == label)
    for voter in voters:
        api(voter).put(f"/ballots/{detail['id']}/vote", {"option_ids": [option["id"]]})
    return api(admin).post(f"/ballots/{detail['id']}/close", {}).json()


def test_one_round_offers_classes_and_subclasses_together(api, champ_admin, season, f1):
    client = api(champ_admin)
    detail = client.post(
        f"/seasons/{season.id}/ballots", {"kind": "car_class", "title": "Clase"}
    ).json()
    candidates = client.get(f"/ballots/{detail['id']}/candidates").json()
    assert [(c["group"], c["label"]) for c in candidates] == [
        ("", "F1"),
        ("F1", "2000s F1"),
        ("F1", "80s F1"),
        ("", "GT3"),
    ]
    _, eighties, _, _ = f1
    detail = client.put(f"/ballots/{detail['id']}/options", {"ids": [eighties.id]}).json()
    assert [o["label"] for o in detail["options"]] == ["F1 › 80s F1"]


def test_two_rounds_offer_only_the_classes_first(api, champ_admin, season, f1):
    parent, eighties, _, gt3 = f1
    client = api(champ_admin)
    detail = client.post(
        f"/seasons/{season.id}/ballots",
        {"kind": "car_class", "title": "Clase", "class_rounds": True},
    ).json()
    candidates = client.get(f"/ballots/{detail['id']}/candidates").json()
    assert [c["label"] for c in candidates] == ["F1", "GT3"]
    refused = client.post(f"/ballots/{detail['id']}/options", {"car_class_id": eighties.id})
    assert refused.json()["detail"] == "subclass_in_class_rounds"


def test_turning_on_two_rounds_removes_the_subclass_options(api, champ_admin, season, f1):
    parent, eighties, _, gt3 = f1
    client = api(champ_admin)
    detail = client.post(f"/seasons/{season.id}/ballots", {"kind": "car_class", "title": "C"})
    ballot_id = detail.json()["id"]
    client.put(f"/ballots/{ballot_id}/options", {"ids": [parent.id, eighties.id]})
    detail = client.patch(f"/ballots/{ballot_id}", {"class_rounds": True}).json()
    assert [o["label"] for o in detail["options"]] == ["F1"]


def test_a_class_with_subclasses_wins_and_a_subclass_round_decides(
    api,
    champ_admin,
    season,
    f1,
    racers,  # noqa: F811
):
    parent, eighties, modern, gt3 = f1
    client = api(champ_admin)
    detail = class_ballot(client, season, [parent.id, gt3.id], class_rounds=True)
    closed = vote_and_close(api, champ_admin, detail, "F1", racers)
    assert closed["status"] == "decided"
    assert list(season.car_classes.all()) == []  # Not yet: the subclass round decides.
    assert len(closed["subclass_rounds"]) == 1 and closed["runoffs"] == []
    round_ = client.get(f"/ballots/{closed['subclass_rounds'][0]['id']}").json()
    assert round_["status"] == "open" and round_["stage"] == "subclass"
    assert round_["title"] == "Clase · F1"
    assert [o["label"] for o in round_["options"]] == ["2000s F1", "80s F1"]
    assert round_["parent"]["id"] == detail["id"]
    vote_and_close(api, champ_admin, round_, "80s F1", racers)
    assert list(season.car_classes.all()) == [eighties]
    entries = SeasonEntry.objects.filter(season=season).select_related("car")
    assert {e.car.key for e in entries} == {"mp4"}


def test_a_class_with_no_subclass_wins_at_once(
    api,
    champ_admin,
    season,
    f1,
    racers,  # noqa: F811
):
    parent, _, _, gt3 = f1
    detail = class_ballot(api(champ_admin), season, [parent.id, gt3.id], class_rounds=True)
    closed = vote_and_close(api, champ_admin, detail, "GT3", racers)
    assert closed["subclass_rounds"] == []
    assert list(season.car_classes.all()) == [gt3]


def test_a_tie_in_a_subclass_round_goes_to_a_runoff(
    api,
    champ_admin,
    season,
    f1,
    racers,  # noqa: F811
):
    parent, _, modern, gt3 = f1
    client = api(champ_admin)
    detail = class_ballot(client, season, [parent.id, gt3.id], class_rounds=True)
    closed = vote_and_close(api, champ_admin, detail, "F1", racers)
    round_ = client.get(f"/ballots/{closed['subclass_rounds'][0]['id']}").json()
    by_label = {o["label"]: o["id"] for o in round_["options"]}
    api(racers[0]).put(f"/ballots/{round_['id']}/vote", {"option_ids": [by_label["80s F1"]]})
    api(racers[1]).put(f"/ballots/{round_['id']}/vote", {"option_ids": [by_label["2000s F1"]]})
    client.post(f"/ballots/{round_['id']}/close", {})
    runoff = client.post(f"/ballots/{round_['id']}/runoff").json()
    assert runoff["stage"] == "runoff" and runoff["title"] == "Clase · F1 · runoff 1"
    vote_and_close(api, champ_admin, runoff, "2000s F1", racers)
    assert Ballot.objects.get(pk=round_["id"]).status == "decided"
    assert list(season.car_classes.all()) == [modern]


def test_a_voter_sees_every_car_of_a_class_option_by_subclass(
    api,
    champ_admin,
    season,
    f1,
    racers,  # noqa: F811
):
    parent, _, _, gt3 = f1
    detail = class_ballot(api(champ_admin), season, [parent.id, gt3.id], class_rounds=True)
    option = next(o for o in detail["options"] if o["label"] == "F1")
    groups = api(racers[0]).get(f"/ballots/{detail['id']}/options/{option['id']}/cars").json()
    assert [(g["subclass"], [c["name"] for c in g["cars"]]) for g in groups] == [
        ("2000s F1", ["F2004"]),
        ("80s F1", ["MP4"]),
    ]
    gt3_option = next(o for o in detail["options"] if o["label"] == "GT3")
    groups = api(racers[0]).get(f"/ballots/{detail['id']}/options/{gt3_option['id']}/cars").json()
    assert groups == [
        {
            "subclass": None,
            "cars": [
                {
                    "id": groups[0]["cars"][0]["id"],
                    "name": "AUDI",
                    "brand": "",
                    "year": None,
                    "image_url": None,
                }
            ],
        }
    ]
