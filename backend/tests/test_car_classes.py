"""Car classes: membership history, class ballots, and class record boards."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import Car, CarClass, CarClassMembership, classes_of
from apps.competition.models import Round

from .test_voting import ballot


@pytest.fixture
def cars(db):
    return [Car.objects.create(key=f"car{n}", name=f"Car {n}") for n in (1, 2, 3)]


def test_class_change_keeps_the_history(api, champ_admin, cars):
    client = api(champ_admin)
    gt3 = client.post("/catalog/classes", {"name": "GT3"}).json()
    client.put(f"/catalog/classes/{gt3['id']}/cars", {"car_ids": [cars[0].id, cars[1].id]})
    # Pretend the first rows started last month, so a change today closes them.
    CarClassMembership.objects.update(valid_from=timezone.localdate() - timedelta(days=30))
    data = client.put(
        f"/catalog/classes/{gt3['id']}/cars",
        {"car_ids": [cars[1].id, cars[2].id], "reason": "BoP 2027"},
    ).json()
    assert data["car_ids"] == [cars[1].id, cars[2].id]
    closed = [h for h in data["history"] if h["valid_to"]]
    assert [h["car_name"] for h in closed] == ["Car 1"]
    yesterday = timezone.localdate() - timedelta(days=1)
    assert classes_of(cars[0].id, yesterday) == [gt3["id"]]
    assert classes_of(cars[0].id, timezone.localdate()) == []


def test_driver_cannot_change_classes(api, driver_user):
    assert api(driver_user).post("/catalog/classes", {"name": "GT3"}).status_code == 403


def test_class_ballot_uses_the_class(api, champ_admin, season):
    client = api(champ_admin)
    gt3 = CarClass.objects.create(name="GT3")
    detail = ballot(client, season, kind="car_class", title="Clase 2027", slots=1)
    response = client.post(f"/ballots/{detail['id']}/options", {"car_class_id": gt3.id})
    option = response.json()["options"][0]
    assert (option["label"], option["car_class_id"]) == ("GT3", gt3.id)


def test_class_record_board(api, make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    client = api(admin)
    client.post(f"/rounds/{round_.id}/result/approve")
    lmdh = CarClass.objects.create(name="LMDh")
    acura = Car.objects.get(key="trr_lmdh_acura_arx-06")
    CarClassMembership.objects.create(
        car_class=lmdh, car=acura, valid_from=round_.scheduled_at.date() - timedelta(days=1)
    )
    data = client.get(f"/records?car_class_id={lmdh.id}&category=race").json()
    assert data["classes"] == [{"id": lmdh.id, "name": "LMDh"}]
    (board,) = data["boards"]
    assert (board["car_id"], board["car_name"]) == (0, "LMDh")
    # Only the Acura is in the class, so the record is the best Acura lap.
    acura_laps = client.get(f"/records?car_id={acura.id}&category=race").json()["boards"]
    assert board["record_ms"] == acura_laps[0]["record_ms"]
