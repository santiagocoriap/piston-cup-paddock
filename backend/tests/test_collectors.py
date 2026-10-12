"""Server collector: its own key, files to the right round as previews, no duplicates."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.catalog.models import Track, TrackLayout
from apps.collectors.models import CollectorEvent, CollectorFile
from apps.competition.models import Round, Season
from apps.imports.models import PenaltyLogFile, ResultImport

NIGHT = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
RACE = "2026_10_11_20_7_RACE.json"
LOG = "race_penalty_20261011_192731.log"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season,
        number=1,
        track_layout=layout,
        scheduled_at=datetime(2026, 10, 11, 19, 0, tzinfo=TZ),
    )


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    assert response.status_code == 201
    return response.json()["key"]


def send(key, name, kind="result", content=None):
    data = content if content is not None else (NIGHT / name).read_bytes()
    if kind == "penalty_log" and content is None:
        data = (NIGHT / "realpenalty" / name).read_bytes()
    return Client().post(
        "/api/collector/files",
        {"kind": kind, "file": SimpleUploadedFile(name, data)},
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )


def test_key_is_needed_and_shown_once(api, champ_admin, championship, key):
    assert Client().get("/api/collector/ping").status_code == 401
    bad = Client().get("/api/collector/ping", HTTP_AUTHORIZATION="Bearer nope")
    assert bad.status_code == 401
    ok = Client().get("/api/collector/ping", HTTP_AUTHORIZATION=f"Bearer {key}")
    assert ok.json() == {"collector": "AC", "championship": championship.name}
    listed = api(champ_admin).get(f"/championships/{championship.id}/collectors").json()
    assert "key" not in listed["collectors"][0]
    assert listed["collectors"][0]["last_seen_at"] is not None


def test_result_file_becomes_a_preview_of_the_round(key, round_):
    response = send(key, RACE)
    assert response.json()["status"] == "assigned"
    assert response.json()["round_id"] == round_.id
    result_import = ResultImport.objects.get()
    assert result_import.status == ResultImport.State.PREVIEW  # An admin still applies it.
    assert result_import.uploaded_by is None
    again = send(key, RACE).json()
    assert again["is_new"] is False
    assert ResultImport.objects.count() == 1


def test_file_without_a_round_waits_for_an_admin(api, champ_admin, key, round_):
    round_.scheduled_at = datetime(2026, 11, 1, 19, 0, tzinfo=TZ)
    round_.save()
    assert send(key, RACE).json()["status"] == "unmatched"
    file_id = CollectorFile.objects.get().id
    response = api(champ_admin).post(f"/collector-files/{file_id}/assign", {"round_id": round_.id})
    assert response.status_code == 200
    assert ResultImport.objects.get().round == round_


def test_round_of_another_championship_cannot_be_chosen(
    api, champ_admin, key, round_, other_championship
):
    other = Season.objects.create(championship=other_championship, name="X", planned_round_count=1)
    foreign = Round.objects.create(season=other, number=1, track_layout=round_.track_layout)
    round_.scheduled_at = None
    round_.save()
    send(key, RACE)
    file_id = CollectorFile.objects.get().id
    response = api(champ_admin).post(f"/collector-files/{file_id}/assign", {"round_id": foreign.id})
    assert response.status_code == 422
    assert ResultImport.objects.count() == 0


def test_newer_copy_of_a_log_replaces_the_preview(key, round_):
    content = (NIGHT / "realpenalty" / LOG).read_bytes()
    lines = content.decode().splitlines(keepends=True)
    first = "".join(lines[: len(lines) // 2]).encode()
    assert send(key, LOG, "penalty_log", first).json()["status"] == "assigned"
    assert send(key, LOG, "penalty_log", content).json()["status"] == "assigned"
    logs = list(PenaltyLogFile.objects.all())
    assert len(logs) == 1 and logs[0].sha256 == CollectorFile.objects.first().sha256
    assert CollectorFile.objects.filter(status="replaced").count() == 1


def test_unreadable_file_is_kept_as_failed(key, round_):
    response = send(key, "2026_10_11_20_7_RACE.json", content=b"not json")
    assert response.json()["status"] == "failed"


def test_events_come_in_once(key):
    batch = {
        "run_id": "run-1",
        "events": [
            {"seq": n, "kind": "collision_car", "at": "2026-10-11T22:30:00Z", "data": {"car": n}}
            for n in range(3)
        ],
    }
    client = Client()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {key}"}
    first = client.post("/api/collector/events", batch, content_type="application/json", **headers)
    again = client.post("/api/collector/events", batch, content_type="application/json", **headers)
    assert (first.json()["new"], again.json()["new"]) == (3, 0)
    assert CollectorEvent.objects.count() == 3


def test_revoked_key_stops_working(api, champ_admin, championship, key):
    listed = api(champ_admin).get(f"/championships/{championship.id}/collectors").json()
    collector_id = listed["collectors"][0]["id"]
    api(champ_admin).post(f"/collectors/{collector_id}/revoke")
    assert (
        Client().get("/api/collector/ping", HTTP_AUTHORIZATION=f"Bearer {key}").status_code == 401
    )


def test_driver_cannot_make_keys(api, driver_user, championship):
    response = api(driver_user).post(f"/championships/{championship.id}/collectors", {"name": "x"})
    assert response.status_code == 403
