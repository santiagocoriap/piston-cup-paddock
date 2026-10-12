"""Position replay of a race start, with incident and restart markers."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
START = datetime(2026, 10, 11, 19, 30, tzinfo=TZ)
GUID = "76561190000000001"


@pytest.fixture
def night(champ_admin, championship, season, layout, car):
    SeasonEntry.objects.create(
        season=season,
        driver=DriverProfile.objects.create(display_name="Driver 1", steam_guid=GUID),
        car=car,
        number=1,
    )
    round_ = Round.objects.create(season=season, number=1, track_layout=layout, scheduled_at=START)
    token, _ = create_token(championship, "AC", champ_admin)
    rows = [
        ("session_started", 0, {"type": 3}),
        ("positions", 1, {"cars": {GUID: [[0, 1.0, 2.0, 0.1], [200, 1.5, 2.5, 0.11]]}}),
        ("collision_env", 2, {"guid": GUID, "speed_kmh": 80, "x": 1.5, "z": 2.5}),
        ("session_started", 60, {"type": 3}),  # The restart.
        ("positions", 61, {"cars": {GUID: [[0, 5.0, 6.0, 0.0]], "car:9": [[0, 7.0, 8.0, 0.0]]}}),
        ("positions", 70, {"cars": {GUID: [[0, 5.5, 6.5, 0.02]]}}),  # A gap of 9 seconds.
        ("session_ended", 90, {}),
    ]
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="run",
            seq=seq,
            kind=kind,
            occurred_at=START + timedelta(seconds=seconds),
            data=data,
        )
    return round_


def test_last_start_is_the_default(api, champ_admin, night):
    data = api(champ_admin).get(f"/rounds/{night.id}/replay").json()
    assert [a["number"] for a in data["attempts"]] == [1, 2]
    assert data["attempt"] == 2 and data["has_positions"] is True
    cars = {c["name"]: c for c in data["cars"]}
    assert cars["Driver 1"]["t_ms"] == [1000, 10000]  # The gap stays: no invented samples.
    assert cars["car:9"]["x"] == [7.0]
    assert data["markers"] == []


def test_abandoned_start_has_incident_and_restart_markers(api, champ_admin, night):
    data = api(champ_admin).get(f"/rounds/{night.id}/replay?attempt=1").json()
    assert data["cars"][0]["t_ms"] == [1000, 1200]
    kinds = [(m["kind"], m["t_ms"]) for m in data["markers"]]
    assert kinds == [("incident", 2000), ("restart", 60000)]
    assert data["markers"][0]["label"] == "Driver 1"
    assert data["duration_ms"] == 60000


def test_round_without_positions(api, champ_admin, season, layout):
    round_ = Round.objects.create(season=season, number=2, track_layout=layout, scheduled_at=START)
    data = api(champ_admin).get(f"/rounds/{round_.id}/replay").json()
    assert data["has_positions"] is False and data["attempts"] == []


def test_other_championship_cannot_see_the_replay(api, make_user, night):
    assert api(make_user("stranger")).get(f"/rounds/{night.id}/replay").status_code == 404
