"""Phase 6: the health of a collector, and the alert for a race with no result file."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Track, TrackLayout
from apps.collectors.alerts import KIND, check_missing_results
from apps.collectors.health import collector_status
from apps.collectors.models import CollectorFile, CollectorToken
from apps.community.models import Notification
from apps.competition.models import Round


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season, number=3, track_layout=layout, scheduled_at=timezone.now()
    )


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()


def send(raw, path, body=None, agent="paddock-collector/1.5.0"):
    client = Client()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {raw}", "HTTP_USER_AGENT": agent}
    if body is None:
        return client.get(f"/api{path}", **headers)
    return client.post(f"/api{path}", body, content_type="application/json", **headers)


def test_the_collector_reports_its_health(api, champ_admin, championship, key):
    send(key["key"], "/collector/ping")
    at = timezone.now().isoformat()
    body = {"queued_files": 3, "last_error": "Upload failed: HTTP 502", "last_error_at": at}
    assert send(key["key"], "/collector/status", body).status_code == 200
    health = api(champ_admin).get(f"/championships/{championship.id}/health").json()
    collector = health["collectors"][0]
    assert collector["version"] == "1.5.0"
    assert collector["queued_files"] == 3
    assert collector["last_error"] == "Upload failed: HTTP 502"
    assert collector["status"] == "running"
    send(key["key"], "/collector/status", {"queued_files": 0, "last_error": ""})
    collector = api(champ_admin).get(f"/championships/{championship.id}/health").json()
    assert collector["collectors"][0]["last_error_at"] is None


def test_the_status_also_saves_the_presets(key):
    body = {"presets": [{"folder": "SERVER_01", "name": "Liga"}], "current": "SERVER_01"}
    send(key["key"], "/collector/status", body)
    token = CollectorToken.objects.get(pk=key["id"])
    assert token.preset == "SERVER_01"


def test_an_off_collector_is_normal_away_from_a_race(championship):
    now = timezone.now()
    token = CollectorToken(championship=championship, last_seen_at=now - timedelta(days=2))
    assert collector_status(token, now, race_now=False) == "off"
    assert collector_status(token, now, race_now=True) == "stopped"


@pytest.fixture
def race_round(round_):
    round_.scheduled_at = timezone.now() - timedelta(hours=4)
    round_.save()
    return round_


def test_a_race_with_no_result_file_alerts_the_admins_once(key, champ_admin, race_round):
    assert check_missing_results() == 1
    notes = Notification.objects.filter(kind=KIND, link=f"/rounds/{race_round.id}")
    assert notes.filter(user=champ_admin).exists()
    assert check_missing_results() == 0  # One time only.
    assert notes.count() == notes.values("user").distinct().count()


def test_no_alert_when_the_file_came_or_before_three_hours(key, race_round, round_):
    CollectorFile.objects.create(
        token_id=key["id"],
        kind=CollectorFile.Kind.RESULT,
        filename="2026_10_14_21_0_RACE.json",
        session_type="race",
        round=race_round,
        status=CollectorFile.State.ASSIGNED,
        sha256="a" * 64,
    )
    assert check_missing_results() == 0
    CollectorFile.objects.all().delete()
    Round.objects.filter(pk=race_round.pk).update(scheduled_at=timezone.now() - timedelta(hours=2))
    assert check_missing_results() == 0


def test_no_alert_without_a_collector(race_round):
    assert check_missing_results() == 0
