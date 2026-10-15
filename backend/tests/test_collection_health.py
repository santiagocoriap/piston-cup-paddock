"""Collection health: collector status, separate problems for each round, and retries."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.collectors.models import CollectorEvent, CollectorToken
from apps.collectors.services import create_token
from apps.competition.models import Round
from apps.core.tasks import ping
from apps.imports.models import ImportedLap
from apps.reports.models import RaceReport

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    return admin, round_, round_.season.championship


def health(api, user, championship):
    return api(user).get(f"/championships/{championship.id}/health").json()


def problems(data):
    return data["rounds"][0]["problems"]


def test_round_without_collector_says_so(api, night):
    admin, _, championship = night
    data = health(api, admin, championship)
    assert data["collectors"] == []
    assert problems(data) == ["no_collector"]


def test_collector_status_running_stopped_never(api, night):
    admin, _, championship = night
    token, _ = create_token(championship, "AC", admin)
    assert health(api, admin, championship)["collectors"][0]["status"] == "never"
    token.last_seen_at = timezone.now()
    token.save()
    assert health(api, admin, championship)["collectors"][0]["status"] == "running"
    token.last_seen_at = timezone.now() - timedelta(minutes=20)
    token.save()
    # Away from a race, a collector that does not run is normal.
    assert health(api, admin, championship)["collectors"][0]["status"] == "off"
    # No file and no event near the round time: the collector did not run that night.
    assert "collector_stopped" in problems(health(api, admin, championship))


def test_partial_events_and_missing_sectors_are_different_problems(api, night):
    admin, round_, championship = night
    token, _ = create_token(championship, "AC", admin)
    CollectorEvent.objects.create(
        token=token,
        run_id="r",
        seq=0,
        kind="lap_completed",
        occurred_at=datetime(2026, 10, 11, 19, 40, tzinfo=TZ),
    )
    lap = ImportedLap.objects.filter(result_import__session__kind="race").first()
    lap.sectors_ms = []
    lap.save()
    data = health(api, admin, championship)
    assert {"partial_events", "missing_sectors"} <= set(problems(data))
    counts = data["rounds"][0]["counts"]
    assert counts["lap_events"] == 1 and counts["laps_without_sectors"] == 1
    assert "collector_stopped" not in problems(data)


def test_admin_retries_a_failed_report(api, night):
    admin, round_, championship = night
    report = RaceReport.objects.create(
        kind="race",
        season=round_.season,
        round=round_,
        number=1,
        result_status="provisional",
        language="es",
        prompt_version="race-2",
        model="m",
        facts={},
        status="failed",
        error="ai_timeout",
    )
    data = health(api, admin, championship)
    assert data["failed"][0] == {
        "kind": "report",
        "id": report.id,
        "label": "2026 R1",
        "error": "ai_timeout",
        "at": None,
    }
    after = api(admin).post(f"/reports/{report.id}/retry").json()
    report.refresh_from_db()
    assert report.status == "pending" and report.error == ""
    assert after["failed"] == []
    assert api(admin).post(f"/reports/{report.id}/retry").status_code == 422


def test_league_admin_retries_a_failed_job(api, night):
    admin, _, championship = night
    job_id = ping.defer()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = %s", [job_id])
    data = health(api, admin, championship)
    assert {"kind": "job", "id": job_id} == {k: data["failed"][0][k] for k in ("kind", "id")}
    api(admin).post(f"/championships/{championship.id}/jobs/{job_id}/retry")
    with connection.cursor() as cursor:
        cursor.execute("SELECT status FROM procrastinate_jobs WHERE id = %s", [job_id])
        assert cursor.fetchone()[0] == "todo"


def test_championship_admin_sees_no_global_jobs(api, champ_admin, championship):
    job_id = ping.defer()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = %s", [job_id])
    data = health(api, champ_admin, championship)
    assert data["failed"] == []
    response = api(champ_admin).post(f"/championships/{championship.id}/jobs/{job_id}/retry")
    assert response.status_code == 403


def test_driver_cannot_see_health(api, driver_user, championship):
    response = api(driver_user).get(f"/championships/{championship.id}/health")
    assert response.status_code == 403
    assert CollectorToken.objects.count() == 0
