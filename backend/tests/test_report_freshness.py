"""Reports follow corrections, regenerate in one click, and use incidents and records."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round
from apps.reports import services
from apps.reports.models import RaceReport
from apps.reports.services import generate

from .test_penalty_logs import NIGHT
from .test_reports import FakeAI


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(services, "litellm", fake)
    return fake


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def make_report(api, admin, round_):
    api(admin).post(f"/rounds/{round_.id}/reports", {"language": "es"})
    return generate(RaceReport.objects.order_by("-id").first().id)


def test_correction_marks_the_report_outdated_and_regenerate_makes_a_new_one(api, night, ai):
    admin, round_ = night
    client = api(admin)
    report = make_report(api, admin, round_)
    listed = client.get(f"/rounds/{round_.id}/reports").json()["reports"]
    assert listed[0]["outdated"] is False

    entry_id = client.get(f"/rounds/{round_.id}").json()["result"][0]["entry_id"]
    client.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": entry_id, "kind": "points", "value": 5, "reason": "Contacto"},
    )
    assert client.get(f"/rounds/{round_.id}/reports").json()["reports"][0]["outdated"] is True

    data = client.post(f"/reports/{report.id}/regenerate").json()
    assert [r["number"] for r in data["reports"]] == [2, 1]
    new = RaceReport.objects.get(number=2)
    assert (new.language, new.tone, new.source_version.number) == (
        report.language,
        report.tone,
        2,
    )


def test_approval_also_makes_the_report_outdated(api, night, ai):
    admin, round_ = night
    make_report(api, admin, round_)
    api(admin).post(f"/rounds/{round_.id}/result/approve")
    reports = api(admin).get(f"/rounds/{round_.id}/reports").json()["reports"]
    # With an AI key, the approval also asks for a new report.
    assert [(r["number"], r["status"]) for r in reports] == [(2, "pending"), (1, "ready")]
    assert reports[1]["outdated"] is True


def test_race_facts_have_incidents_and_records(api, night, ai):
    admin, round_ = night
    token, _ = create_token(round_.season.championship, "AC", admin)
    for seq, (kind, data) in enumerate(
        [
            ("session_started", {"type": 3}),
            ("collision_env", {"guid": "76561190000000001", "speed_kmh": 90}),
        ]
    ):
        CollectorEvent.objects.create(
            token=token,
            run_id="r",
            seq=seq,
            kind=kind,
            occurred_at=round_.scheduled_at + timedelta(seconds=seq * 60),
            data=data,
        )
    api(admin).post(f"/rounds/{round_.id}/result/approve")
    facts = make_report(api, admin, round_).facts
    assert facts["incidents"][0]["drivers"] == ["Driver 01"]
    assert "no_incident_data" not in facts["data_gaps"]
    race_record = next(r for r in facts["records"] if r["category"] == "race")
    assert (race_record["driver"], race_record["kind"]) == ("Driver 01", "new_record")


def test_season_facts_have_progression_and_safety(api, night, ai):
    admin, round_ = night
    api(admin).post(f"/rounds/{round_.id}/result/approve")
    api(admin).post(f"/seasons/{round_.season.id}/reports", {"language": "es"})
    facts = RaceReport.objects.get(kind="season").facts
    assert facts["title_progression"] == [
        {
            "ref": f"standings:season:{round_.season.id}:after_round:1",
            "round": 1,
            "leaders": ["Driver 01"],
            "points": 25,
        }
    ]
    assert facts["records"]
    assert facts["safety"] == []  # No collector events: every rating is unknown.


def test_provisional_report_after_the_race_file(
    api, champ_admin, championship, season, ai, django_capture_on_commit_callbacks
):
    import json

    from apps.catalog.models import Car, Track, TrackLayout
    from apps.competition.models import SeasonEntry
    from apps.identity.models import DriverProfile
    from apps.imports.ac_results import parse

    championship.provisional_reports = True
    championship.save()
    content = (NIGHT / "2026_10_11_20_7_RACE.json").read_bytes()
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    for n, driver in enumerate(parse(json.loads(content)).drivers, start=1):
        car, _ = Car.objects.get_or_create(key=driver.car_model.lower(), defaults={"name": "c"})
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=driver.name, steam_guid=driver.guid),
            car=car,
            number=n,
        )
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    client = api(champ_admin)
    upload = client.client.post(
        f"/api/rounds/{round_.id}/imports",
        {"file": SimpleUploadedFile("2026_10_11_20_7_RACE.json", content)},
    )
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/imports/{upload.json()['id']}/apply", {})
    report = RaceReport.objects.get()
    assert (report.result_status, report.tone) == ("provisional", "sarcastic")


def test_championship_setting_needs_an_admin(api, driver_user, champ_admin, championship):
    url = f"/championships/{championship.id}/settings"
    assert (
        api(driver_user)
        .client.patch(f"/api{url}", {"provisional_reports": True}, content_type="application/json")
        .status_code
        == 403
    )
    response = api(champ_admin).client.patch(
        f"/api{url}", {"provisional_reports": True}, content_type="application/json"
    )
    assert response.json()["provisional_reports"] is True
