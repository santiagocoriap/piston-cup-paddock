"""Track records from the real, sanitized race night in samples/."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Attempt, Round, SeasonEntry
from apps.identity.models import DriverProfile

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
GUIDS = {
    "Driver 01": "76561190000000001",
    "Driver 03": "76561190000000003",
    "Driver 06": "76561190000000006",
    "Driver 05": "76561190000000005",
    "Driver 04": "76561190000000004",
}


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-11T22:00Z"
    )


@pytest.fixture
def entries(season):
    car = Car.objects.create(key="trr_lmdh_acura_arx-06", name="Acura")
    return {
        name: SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name, steam_guid=guid),
            car=car,
            number=n,
        )
        for n, (name, guid) in enumerate(GUIDS.items(), start=1)
    }


@pytest.fixture
def admin(api, champ_admin):
    return api(champ_admin)


def apply_file(client, round_, name):
    content = (SAMPLES / name).read_bytes()
    upload = client.client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile(name, content, content_type="application/json")},
    )
    response = client.post(f"/imports/{upload.json()['id']}/apply", {})
    assert response.status_code == 200, response.json()


@pytest.fixture
def raced(admin, round_, entries):
    apply_file(admin, round_, "2026_10_11_18_54_QUALIFY.json")
    apply_file(admin, round_, "2026_10_11_20_7_RACE.json")
    return round_


def board(client, category):
    data = client.get("/records").json()
    return next((b for b in data["boards"] if b["category"] == category), None)


def test_no_record_before_the_result_is_official(admin, raced):
    assert admin.get("/records").json()["boards"] == []


def test_race_and_qualifying_laps_make_separate_records(admin, raced):
    admin.post(f"/rounds/{raced.id}/result/approve")
    race = board(admin, "race")
    qualifying = board(admin, "qualifying")
    assert race["record_ms"] == 189296  # Driver 01, best lap of the race file.
    assert race["holders"][0]["driver_name"] == "Driver 01"
    assert qualifying["record_ms"] == 190686  # Driver 03, best lap of the qualifying file.
    assert (race["track_name"], race["layout_name"], race["car_name"]) == (
        "Highlands",
        "Long",
        "Acura",
    )


def test_record_shows_conditions_handicaps_and_provenance(admin, raced):
    admin.post(f"/rounds/{raced.id}/result/approve")
    holder = board(admin, "race")["holders"][0]
    assert holder["conditions"] is None
    assert (holder["ballast_kg"], holder["restrictor"]) == (8, 0)
    assert holder["source_file"] == "2026_10_11_20_7_RACE.json"
    assert len(holder["sectors_ms"]) == 3


def test_dsq_driver_loses_the_race_record_and_the_history_keeps_it(admin, raced, entries):
    admin.post(f"/rounds/{raced.id}/result/approve")
    admin.post(
        f"/rounds/{raced.id}/penalties",
        {"entry_id": entries["Driver 01"].id, "kind": "dsq", "reason": "Peso ilegal"},
    )
    race = board(admin, "race")
    assert race["holders"][0]["driver_name"] == "Driver 03"
    assert race["record_ms"] == 190680
    removed = [h for h in race["history"] if h["kind"] == "removed"]
    assert removed[0]["lap"]["driver_name"] == "Driver 01"
    assert removed[0]["lap"]["ineligible_reason"] == "dsq"


def test_invalid_lap_gives_the_record_to_the_next_lap(admin, raced):
    admin.post(f"/rounds/{raced.id}/result/approve")
    lap_id = board(admin, "race")["holders"][0]["lap_id"]
    assert admin.post(f"/laps/{lap_id}/invalidate", {"reason": "Corte"}).status_code == 204
    race = board(admin, "race")
    assert race["record_ms"] > 189296
    assert any(h["lap"]["lap_id"] == lap_id for h in race["history"])


def test_laps_of_an_abandoned_start_are_not_records(admin, raced):
    admin.post(f"/rounds/{raced.id}/result/approve")
    Attempt.objects.filter(session__round=raced, session__kind="race").update(status="abandoned")
    race = board(admin, "race")
    assert race["record_ms"] is None
    assert all(h["lap"]["ineligible_reason"] == "abandoned_attempt" for h in race["history"])


def test_user_outside_the_championship_sees_no_records(api, admin, raced, make_user):
    admin.post(f"/rounds/{raced.id}/result/approve")
    assert api(make_user("outsider")).get("/records").json()["boards"] == []


def test_driver_cannot_invalidate_a_lap(api, admin, driver_user, raced):
    admin.post(f"/rounds/{raced.id}/result/approve")
    lap_id = board(admin, "race")["holders"][0]["lap_id"]
    response = api(driver_user).post(f"/laps/{lap_id}/invalidate", {"reason": "x"})
    assert response.status_code == 403
