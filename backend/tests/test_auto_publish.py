"""Phase 1: a clean collector file becomes a provisional result with no admin click."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.audit.models import AuditEntry
from apps.catalog.models import Car, Track, TrackLayout
from apps.community.models import Notification
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.imports.models import PenaltyLogFile, ResultImport
from apps.restarts.models import Restart
from apps.results.models import Penalty, RaceResult

NIGHT = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
RACE = "2026_10_11_20_7_RACE.json"
FINAL_LOG = "race_penalty_20261011_192731.log"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# The five drivers of the race file, with the car of each one.
GRID = {
    "76561190000000001": ("Driver 01", "TRR_LMDh_acura_arx-06"),
    "76561190000000003": ("Driver 03", "TRR_LMDh_cadillac_v-series.r"),
    "76561190000000006": ("Driver 06", "TRR_LMH_vanwall_vandervell_680_p"),
    "76561190000000005": ("Driver 05", "TRR_LMH_vanwall_vandervell_680_p"),
    "76561190000000004": ("Driver 04", "TRR_LMDh_cadillac_v-series.r"),
}


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
def entries(season):
    cars = {}
    rows = {}
    for number, (guid, (name, model)) in enumerate(GRID.items(), start=1):
        car = cars.get(model) or Car.objects.create(key=model.lower(), name=model)
        cars[model] = car
        rows[guid] = SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name, steam_guid=guid),
            car=car,
            number=number,
        )
    return rows


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()["key"]


def clean_race() -> bytes:
    """The race file with no problem: one GUID for each driver, and no ballast or restrictor,
    as the rules give to every driver in the first round."""
    data = json.loads((NIGHT / RACE).read_text(encoding="utf-8"))
    for block in ("Cars", "Result", "Laps"):
        for row in data[block]:
            row["BallastKG"] = 0
            row["Restrictor"] = 0
    for row in data["Result"]:
        if row["DriverName"] == "Driver 04":
            row["DriverGuid"] = "76561190000000004"
    return json.dumps(data).encode("utf-8")


def send(key, name, kind="result", content=None):
    if content is None:
        folder = NIGHT / "realpenalty" if kind == "penalty_log" else NIGHT
        content = (folder / name).read_bytes()
    return Client().post(
        "/api/collector/files",
        {"kind": kind, "file": SimpleUploadedFile(name, content)},
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )


def race_logs() -> list[str]:
    return sorted(p.name for p in (NIGHT / "realpenalty").glob("race_penalty_*.log"))


def test_clean_race_file_is_published_with_no_admin(key, round_, entries):
    assert send(key, RACE, content=clean_race()).status_code == 200

    result_import = ResultImport.objects.get()
    assert result_import.status == ResultImport.State.APPLIED
    assert result_import.auto_status == ResultImport.AutoState.APPLIED
    result = RaceResult.objects.get(round=round_)
    assert result.status == RaceResult.State.PROVISIONAL  # An admin still approves it.
    flagged = {flag["entry_id"] for flag in result_import.review_flags}
    lapped = {
        entries[g].id for g in ("76561190000000006", "76561190000000005", "76561190000000004")
    }
    assert flagged == lapped  # Fewer laps than the winner: the admin checks for a DNF.
    entry = AuditEntry.objects.get(action="import.auto_applied")
    assert (entry.actor_name, entry.actor_id) == ("collector", None)


def test_file_with_a_problem_waits_for_an_admin(api, champ_admin, key, round_, entries):
    send(key, RACE)  # The real file: one GUID differs, and the handicaps differ from the rules.

    result_import = ResultImport.objects.get()
    assert result_import.status == ResultImport.State.PREVIEW
    assert result_import.auto_status == ResultImport.AutoState.BLOCKED
    assert {"guid_differs_in_result", "handicap_differs"} <= set(result_import.auto_reasons)
    assert not RaceResult.objects.filter(round=round_).exists()
    assert Notification.objects.filter(user=champ_admin, kind="import.blocked").exists()
    pending = api(champ_admin).get("/pending").json()
    assert any(item["kind"] == "imports" and item["count"] == 1 for item in pending)
    shown = api(champ_admin).get(f"/rounds/{round_.id}/imports").json()[0]
    assert shown["auto_status"] == "blocked"


def test_setting_off_keeps_the_preview(api, champ_admin, championship, key, round_, entries):
    response = api(champ_admin).client.patch(
        f"/api/championships/{championship.id}/settings",
        {"auto_publish_results": False},
        content_type="application/json",
    )
    assert response.json()["auto_publish_results"] is False
    assert response.json()["provisional_reports"] is False  # The other setting stays.
    send(key, RACE, content=clean_race())
    result_import = ResultImport.objects.get()
    assert (result_import.status, result_import.auto_status) == ("preview", "")


def test_a_second_race_file_waits_for_an_admin(key, round_, entries):
    send(key, RACE, content=clean_race())
    changed = json.loads(clean_race())
    changed["Laps"] = changed["Laps"][:-1]
    send(key, "2026_10_11_20_9_RACE.json", content=json.dumps(changed).encode("utf-8"))

    second = ResultImport.objects.get(filename="2026_10_11_20_9_RACE.json")
    assert second.auto_reasons == ["result_exists"]
    assert RaceResult.objects.get(round=round_).versions.count() == 1


def test_restarts_and_served_penalties_come_in_with_the_final_log(key, round_, entries):
    logs = race_logs()
    for name in logs[:-1]:  # The collector sends each abandoned start when a newer one starts.
        send(key, name, kind="penalty_log")
    send(key, RACE, content=clean_race())
    assert Restart.objects.count() == 0  # The final log is not here yet.
    assert PenaltyLogFile.objects.filter(status=ResultImport.State.PREVIEW).count() == len(logs) - 1

    send(key, logs[-1], kind="penalty_log")  # About 10 minutes after the race.

    assert Restart.objects.count() == len(logs) - 1
    assert not PenaltyLogFile.objects.filter(status=ResultImport.State.PREVIEW).exists()
    served = Penalty.objects.filter(source=Penalty.Source.REAL_PENALTY)
    assert served.exists()
    assert set(served.values_list("kind", flat=True)) == {"served"}
    assert AuditEntry.objects.filter(action="penalty_logs.auto_applied").exists()


def test_logs_before_the_result_wait_for_the_result(key, round_, entries):
    for name in race_logs():
        send(key, name, kind="penalty_log")
    assert Restart.objects.count() == 0  # No result yet.

    send(key, RACE, content=clean_race())
    assert Restart.objects.count() == len(race_logs()) - 1
