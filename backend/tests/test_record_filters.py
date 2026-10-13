"""Record filters, conditions, and manual historical records."""

import pytest
from django.core.management import call_command

from apps.catalog.models import Car
from apps.competition.models import ChampionshipMember, Round
from apps.records.models import ManualRecord


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    round_.announced_conditions = {"weather": "Despejado", "air_temp_c": 22}
    round_.save()
    return admin, round_


def boards(client, query=""):
    return client.get(f"/records{query}").json()


def test_filters_and_the_overall_board(api, night):
    admin, round_ = night
    client = api(admin)
    client.post(f"/rounds/{round_.id}/result/approve")
    every = boards(client)
    assert len(every["cars"]) > 1 and every["seasons"][0]["id"] == round_.season.id
    race = boards(client, "?category=race")
    assert {b["category"] for b in race["boards"]} == {"race"}
    acura = Car.objects.get(key="trr_lmdh_acura_arx-06")
    by_car = boards(client, f"?car_id={acura.id}")
    assert {b["car_id"] for b in by_car["boards"]} == {acura.id}
    overall = boards(client, "?overall=true&category=race")["boards"]
    assert len(overall) == 1 and overall[0]["car_id"] == 0
    assert overall[0]["holders"][0]["lap_time_ms"] == 189296
    assert overall[0]["holders"][0]["conditions"] == {"weather": "Despejado", "air_temp_c": 22}
    assert boards(client, "?season_id=999999")["boards"] == []


def test_manual_record_is_unverified_until_an_admin_verifies_it(api, night):
    admin, round_ = night
    client = api(admin)
    acura = Car.objects.get(key="trr_lmdh_acura_arx-06")
    response = client.post(
        "/records/manual",
        {
            "championship_id": round_.season.championship_id,
            "layout_id": round_.track_layout_id,
            "car_id": acura.id,
            "category": "race",
            "lap_time_ms": 185000,
            "driver_name": "Leyenda",
            "date": "2025-03-01",
            "source": "Captura de la liga vieja",
        },
    )
    assert response.status_code == 201
    board = boards(client, f"?car_id={acura.id}&category=race")["boards"][0]
    holder = board["holders"][0]
    assert (holder["driver_name"], holder["manual"], holder["verified"]) == ("Leyenda", True, False)
    assert holder["source_file"] == "Captura de la liga vieja"
    client.post(f"/records/manual/{holder['manual_id']}/verify")
    holder = boards(client, f"?car_id={acura.id}&category=race")["boards"][0]["holders"][0]
    assert holder["verified"] is True
    # A season filter leaves out manual records, which have no season.
    season = boards(client, f"?car_id={acura.id}&season_id={round_.season.id}")["boards"]
    assert all(not h["manual"] for b in season for h in b["holders"])
    client.client.delete(f"/api/records/manual/{holder['manual_id']}")
    assert ManualRecord.objects.count() == 0


def test_driver_cannot_add_manual_records(api, night, make_user):
    _, round_ = night
    racer = make_user("racer")
    ChampionshipMember.objects.create(
        championship=round_.season.championship, user=racer, role=ChampionshipMember.Role.DRIVER
    )
    response = api(racer).post(
        "/records/manual",
        {
            "championship_id": round_.season.championship_id,
            "layout_id": round_.track_layout_id,
            "car_id": Car.objects.first().id,
            "category": "race",
            "lap_time_ms": 185000,
            "driver_name": "x",
            "date": "2025-03-01",
            "source": "x",
        },
    )
    assert response.status_code == 403
