"""Back up a league with real data, delete everything, restore, and compare."""

import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile, User
from apps.imports.models import ImportedLap, ResultImport

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands"
RACE = "2026_10_11_20_7_RACE.json"
GUIDS = [
    "76561190000000001",
    "76561190000000003",
    "76561190000000006",
    "76561190000000005",
    "76561190000000004",
]

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def league_with_history(api, champ_admin, season):
    """A round with an imported race file, an official result, a penalty, and a restart."""
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    car = Car.objects.create(key="trr_lmdh_acura_arx-06", name="Acura")
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}", steam_guid=guid),
            car=car,
            number=n,
        )
        for n, guid in enumerate(GUIDS, start=1)
    ]
    round_ = Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-11T22:00Z"
    )
    client = api(champ_admin)
    client.post(f"/rounds/{round_.id}/restarts", {"reason": "first_lap_crash"})
    upload = client.client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile(RACE, (SAMPLES / RACE).read_bytes())},
    )
    client.post(f"/imports/{upload.json()['id']}/apply", {})
    client.post(f"/rounds/{round_.id}/result/approve")
    client.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": entries[0].id, "kind": "positions", "value": 1, "reason": "Corte"},
    )
    return client, round_


def snapshot(client, round_):
    detail = client.get(f"/rounds/{round_.id}").json()
    return {
        "result": [(r["driver_name"], r["position"], r["points"]) for r in detail["result"]],
        "status": detail["status"],
        "versions": len(detail["versions"]),
        "penalties": len(detail["penalties"]),
        "standings": client.get(f"/seasons/{round_.season_id}/standings").json(),
        "restarts": client.get(f"/rounds/{round_.id}/restarts").json()["summary"]["total"],
        "audit": len(client.get("/audit").json()),
        "records": client.get("/records").json()["boards"],
    }


def test_restore_gives_back_the_full_history(league_with_history, tmp_path, champ_admin, api):
    client, round_ = league_with_history
    before = snapshot(client, round_)
    stored = ResultImport.objects.get()
    evidence = Path(stored.file.path).read_bytes()
    output = tmp_path / "backup.zip"

    call_command("backup", output=str(output))
    with zipfile.ZipFile(output) as archive:
        assert "data.json" in archive.namelist()
        assert any(name.startswith("media/results/") for name in archive.namelist())

    # Delete everything, also the stored file.
    call_command("flush", interactive=False, verbosity=0)
    Path(stored.file.path).unlink()
    assert User.objects.count() == 0

    call_command("restore", str(output), confirm=True)

    client = api(User.objects.get(username="organizer"))
    assert snapshot(client, Round.objects.get()) == before
    assert Path(ResultImport.objects.get().file.path).read_bytes() == evidence
    assert ImportedLap.objects.count() == 36


def test_restore_needs_the_confirm_flag(tmp_path, league_with_history):
    output = tmp_path / "backup.zip"
    call_command("backup", output=str(output))
    with pytest.raises(CommandError, match="--confirm"):
        call_command("restore", str(output))
    assert Round.objects.count() == 1


def test_restore_refuses_a_file_that_is_not_a_backup(tmp_path, db):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("hello.txt", "x")
    with pytest.raises(CommandError, match="not a Piston Cup Paddock backup"):
        call_command("restore", str(bad), confirm=True)


def test_exports_give_csv_files(league_with_history):
    client, round_ = league_with_history
    season_id = round_.season_id
    results = client.client.get(f"/api/seasons/{season_id}/export/results.csv")
    assert results["Content-Type"].startswith("text/csv")
    lines = results.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("round,track,layout,result_status,version,position")
    assert len(lines) == 6  # Header and five drivers.
    assert ",1,finished,2,D2," in lines[1]  # D1 lost one position, so D2 won.

    standings = client.client.get(f"/api/seasons/{season_id}/export/standings.csv")
    assert standings.content.decode("utf-8-sig").splitlines()[0].endswith(",R1")

    restarts = client.client.get(f"/api/seasons/{season_id}/export/restarts.csv")
    assert "first_lap_crash" in restarts.content.decode("utf-8-sig")

    records = client.client.get("/api/records/export.csv").content.decode("utf-8-sig")
    assert "Highlands,Long,Acura,race,189296,D1" in records


def test_user_outside_the_championship_cannot_export(api, make_user, season):
    response = api(make_user("outsider")).client.get(f"/api/seasons/{season.id}/export/results.csv")
    assert response.status_code == 404


def test_formula_in_a_driver_name_stays_text(league_with_history):
    client, round_ = league_with_history
    DriverProfile.objects.filter(display_name="D2").update(display_name="=HYPERLINK(1)")
    content = client.client.get(f"/api/seasons/{round_.season_id}/export/results.csv")
    text = content.content.decode("utf-8-sig")
    assert ",'=HYPERLINK(1)," in text
    assert ",=HYPERLINK" not in text
    assert ",-" not in text.splitlines()[1]  # Numbers keep no quote.
