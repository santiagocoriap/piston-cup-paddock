"""Import the real, sanitized race night from samples/ into a round."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.imports.models import ImportedLap, ResultImport
from apps.results.models import ResultVersion

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
RACE = "2026_10_11_20_7_RACE.json"
QUALIFY = "2026_10_11_18_54_QUALIFY.json"

# The five drivers with laps in the race file, by fake GUID.
GRID = {
    "76561190000000001": ("Driver 01", "TRR_LMDh_acura_arx-06"),
    "76561190000000003": ("Driver 03", "x"),
    "76561190000000006": ("Driver 06", "x"),
    "76561190000000005": ("Driver 05", "x"),
    "76561190000000004": ("Driver 04", "x"),
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
        guid: SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name, steam_guid=guid),
            car=car,
            number=n,
        )
        for n, (guid, (name, _)) in enumerate(GRID.items(), start=1)
    }


def upload(client, round_, name=RACE):
    content = (SAMPLES / name).read_bytes()
    return client.client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile(name, content, content_type="application/json")},
    )


def test_preview_matches_drivers_by_guid(api, champ_admin, round_, entries):
    response = upload(api(champ_admin), round_)
    assert response.status_code == 201
    preview = response.json()["preview"]
    assert preview["session_type"] == "race"
    assert preview["attempt"] == 1
    assert preview["unmatched"] == []
    assert [d["driver_name"] for d in preview["drivers"]] == [
        "Driver 01",
        "Driver 03",
        "Driver 06",
        "Driver 05",
        "Driver 04",
    ]
    assert "conditions" in preview["missing"]
    assert preview["warnings"] == []


def test_preview_lists_unmatched_drivers_and_warnings(api, champ_admin, round_, entries):
    entries["76561190000000006"].driver.steam_guid = None
    entries["76561190000000006"].driver.save()
    preview = upload(api(champ_admin), round_).json()["preview"]
    assert [d["guid"] for d in preview["unmatched"]] == ["76561190000000006"]
    car_3 = next(d for d in preview["drivers"] if d["guid"] == "76561190000000004")
    assert "guid_differs_in_result" in car_3["warnings"]
    assert "fewer_laps" in car_3["warnings"]


def test_display_name_does_not_match_a_driver(api, champ_admin, round_, entries):
    for entry in entries.values():
        entry.driver.steam_guid = None
        entry.driver.save()
    preview = upload(api(champ_admin), round_).json()["preview"]
    assert preview["drivers"] == []
    assert len(preview["unmatched"]) == 5


def test_apply_enters_the_result_and_keeps_the_file(api, champ_admin, round_, entries):
    client = api(champ_admin)
    import_id = upload(client, round_).json()["id"]
    statuses = {str(entries["76561190000000004"].id): "dnf"}
    applied = client.post(f"/imports/{import_id}/apply", {"statuses": statuses})
    assert applied.json()["status"] == "applied"

    detail = client.get(f"/rounds/{round_.id}").json()
    assert [(r["driver_name"], r["points"]) for r in detail["result"]] == [
        ("Driver 01", 25),
        ("Driver 03", 18),
        ("Driver 06", 15),
        ("Driver 05", 12),
        ("Driver 04", 10),
    ]
    assert detail["result"][4]["status"] == "dnf"
    assert ImportedLap.objects.count() == 36
    stored = ResultImport.objects.get()
    assert stored.file.read() == (SAMPLES / RACE).read_bytes()


def test_second_upload_of_the_same_file_adds_nothing(api, champ_admin, round_, entries):
    client = api(champ_admin)
    first = upload(client, round_).json()
    client.post(f"/imports/{first['id']}/apply", {})
    again = upload(client, round_)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert again.json()["status"] == "applied"
    refused = client.post(f"/imports/{first['id']}/apply", {})
    assert refused.json()["detail"] == "already_applied"
    assert ResultImport.objects.count() == 1
    assert ResultVersion.objects.count() == 1
    assert ImportedLap.objects.count() == 36


def test_unmatched_driver_blocks_the_apply_until_linked_or_ignored(
    api, champ_admin, round_, entries
):
    driver = entries["76561190000000005"].driver
    driver.steam_guid = None
    driver.save()
    client = api(champ_admin)
    import_id = upload(client, round_).json()["id"]
    assert client.post(f"/imports/{import_id}/apply", {}).json()["detail"] == "unmatched_drivers"

    linked = client.post(
        f"/imports/{import_id}/link",
        {"guid": "76561190000000005", "entry_id": entries["76561190000000005"].id},
    )
    assert linked.json()["preview"]["unmatched"] == []
    assert client.post(f"/imports/{import_id}/apply", {}).status_code == 200


def test_ignored_guest_is_left_out_of_the_classification(api, champ_admin, round_, entries):
    entries["76561190000000003"].driver.steam_guid = None
    entries["76561190000000003"].driver.save()
    client = api(champ_admin)
    import_id = upload(client, round_).json()["id"]
    client.post(f"/imports/{import_id}/apply", {"ignored_guids": ["76561190000000003"]})
    result = client.get(f"/rounds/{round_.id}").json()["result"]
    assert [(r["driver_name"], r["position"]) for r in result][:2] == [
        ("Driver 01", 1),
        ("Driver 06", 2),
    ]


def test_qualifying_file_stores_laps_but_no_result(api, champ_admin, round_, entries):
    client = api(champ_admin)
    import_id = upload(client, round_, QUALIFY).json()["id"]
    client.post(f"/imports/{import_id}/apply", {})
    assert ImportedLap.objects.count() == 13
    assert client.get(f"/rounds/{round_.id}").json()["result"] is None


def test_wrong_track_shows_a_warning(api, champ_admin, round_, entries):
    round_.track_layout.key = "layout_short"
    round_.track_layout.save()
    preview = upload(api(champ_admin), round_).json()["preview"]
    assert preview["warnings"] == ["track_differs"]


def test_not_a_result_file_is_refused(api, champ_admin, round_):
    response = api(champ_admin).client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile("x.json", b"{}", content_type="application/json")},
    )
    assert response.json()["detail"] == "not_a_result_file"


def test_driver_cannot_upload(api, driver_user, round_):
    assert upload(api(driver_user), round_).status_code == 403
