"""Import the real race night: the AC files first, then all Real Penalty logs."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Attempt, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.imports.models import ImportedLap
from apps.restarts.models import Restart
from apps.results.models import Penalty, ResultVersion

NIGHT = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
GUIDS = [
    "76561190000000001",
    "76561190000000003",
    "76561190000000006",
    "76561190000000005",
    "76561190000000004",
]


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    car = Car.objects.create(key="trr_lmdh_acura_arx-06", name="Acura")
    for n, guid in enumerate(GUIDS, start=1):
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}", steam_guid=guid),
            car=car,
            number=n,
        )
    return Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-11T22:00Z"
    )


@pytest.fixture
def admin(api, champ_admin):
    return api(champ_admin)


def apply_file(admin, round_, name):
    upload = admin.client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile(name, (NIGHT / name).read_bytes())},
    )
    admin.post(f"/imports/{upload.json()['id']}/apply", {})


def upload_logs(admin, round_, pattern="*.log"):
    files = [
        SimpleUploadedFile(p.name, p.read_bytes())
        for p in sorted((NIGHT / "realpenalty").glob(pattern))
    ]
    return admin.client.post(f"/api/rounds/{round_.id}/penalty-logs", {"files": files})


@pytest.fixture
def raced(admin, round_):
    apply_file(admin, round_, "2026_10_11_18_54_QUALIFY.json")
    apply_file(admin, round_, "2026_10_11_20_7_RACE.json")
    return round_


def test_preview_finds_20_abandoned_starts_and_the_served_penalty(admin, raced):
    data = upload_logs(admin, raced).json()
    assert data["new_files"] == 23
    assert data["final_log"] == "race_penalty_20261011_192731.log"
    assert len(data["starts"]) == 20
    assert all(start["new"] for start in data["starts"])
    served = [p for p in data["penalties"] if p["kind"] == "served"]
    assert [(p["driver_name"], p["penalty"]) for p in served] == [("D2", "Stop & go 5 seconds")]
    assert not [p for p in data["penalties"] if p["kind"] == "time"]
    assert data["ignored_penalties"] > 0  # The time penalties of abandoned starts.
    assert data["invalid_laps"][0]["lap_id"] is not None


def test_apply_adds_the_restarts_before_the_accepted_race(admin, raced):
    data = upload_logs(admin, raced).json()
    keys = [p["key"] for p in data["penalties"] if p["kind"] == "served"]
    admin.post(f"/rounds/{raced.id}/penalty-logs/apply", {"penalty_keys": keys})

    attempts = list(
        Attempt.objects.filter(session__round=raced, session__kind="race").order_by("number")
    )
    assert len(attempts) == 21
    assert [a.status for a in attempts[:20]] == ["abandoned"] * 20
    assert attempts[-1].status == "accepted"
    assert Restart.objects.count() == 20
    assert Restart.objects.get(abandoned_attempt=attempts[19]).replacement_attempt == attempts[20]
    summary = admin.get(f"/rounds/{raced.id}/restarts").json()["summary"]
    assert summary["total"] == 20


def test_served_penalty_is_recorded_but_changes_nothing(admin, raced):
    before = admin.get(f"/rounds/{raced.id}").json()["result"]
    data = upload_logs(admin, raced).json()
    keys = [p["key"] for p in data["penalties"] if p["kind"] == "served"]
    after = admin.post(f"/rounds/{raced.id}/penalty-logs/apply", {"penalty_keys": keys}).json()
    detail = admin.get(f"/rounds/{raced.id}").json()
    assert detail["result"] == before
    assert detail["penalties"][0]["kind"] == "served"
    assert ResultVersion.objects.count() == 1
    assert after["penalties"][0]["already"] is True


def test_second_apply_and_second_upload_add_nothing(admin, raced):
    data = upload_logs(admin, raced).json()
    keys = [p["key"] for p in data["penalties"] if p["kind"] == "served"]
    admin.post(f"/rounds/{raced.id}/penalty-logs/apply", {"penalty_keys": keys})
    again = upload_logs(admin, raced).json()
    assert again["new_files"] == 0
    admin.post(f"/rounds/{raced.id}/penalty-logs/apply", {"penalty_keys": keys})
    assert Restart.objects.count() == 20
    assert Penalty.objects.count() == 1


def test_invalid_qualifying_lap_is_marked(admin, raced):
    upload_logs(admin, raced)
    admin.post(f"/rounds/{raced.id}/penalty-logs/apply", {"penalty_keys": []})
    lap = ImportedLap.objects.get(lap_time_ms=336531)
    assert lap.invalid_reason == "Real Penalty: invalid qualifying lap"


def test_time_penalty_changes_the_order_with_the_file_times(admin, raced):
    """The race file gives laps and total times, so a time penalty can work."""
    result = admin.get(f"/rounds/{raced.id}").json()["result"]
    winner, second = result[0], result[1]
    response = admin.post(
        f"/rounds/{raced.id}/penalties",
        {"entry_id": winner["entry_id"], "kind": "time", "value": 200, "reason": "Corte"},
    )
    order = [line["entry_id"] for line in response.json()["result"]]
    assert order[0] == second["entry_id"]


def test_time_penalty_needs_times(api, champ_admin, round_):
    admin = api(champ_admin)
    entry = SeasonEntry.objects.first()
    admin.put(
        f"/rounds/{round_.id}/result",
        {"lines": [{"entry_id": entry.id, "status": "finished", "position": 1}]},
    )
    response = admin.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": entry.id, "kind": "time", "value": 5, "reason": "x"},
    )
    assert response.json()["detail"] == "time_penalty_needs_times"


def test_restarts_recorded_by_hand_are_not_added_again(admin, round_):
    admin.post(f"/rounds/{round_.id}/restarts", {"reason": "first_lap_crash"})
    data = upload_logs(admin, round_, "race_penalty_20261011_18*.log").json()
    # Four race logs: three abandoned starts, and one restart is already there.
    assert [s["new"] for s in data["starts"]] == [False, True, True]
    assert "some_restarts_recorded" in data["warnings"]


def test_driver_cannot_upload_logs(api, driver_user, round_):
    assert upload_logs(api(driver_user), round_).status_code == 403
