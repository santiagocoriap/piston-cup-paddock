"""Restart assistance: suggestion from the first collision, incident links, corrections, and
track guidance in the briefing."""

from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round, SeasonEntry
from apps.restarts.models import Restart

D1, D5 = "76561190000000001", "76561190000000005"


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    token, _ = create_token(round_.season.championship, "AC", admin)
    rows = [
        ("session_started", 0, {"type": 3}),  # Start 1.
        ("collision_env", 20, {"guid": D5, "speed_kmh": 80}),  # D5 crashes first.
        ("collision_car", 22, {"guid": D1, "speed_kmh": 60, "other": {"guid": D5}}),
        ("session_started", 120, {"type": 3}),  # Start 2.
    ]
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="r",
            seq=seq,
            kind=kind,
            occurred_at=round_.scheduled_at + timedelta(seconds=seconds),
            data=data,
        )
    return admin, round_


def test_first_collision_gives_a_suggestion_and_incidents(api, night):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/restarts").json()
    first = next(r for r in data["restarts"] if r["abandoned_attempt"] == 1)
    assert [s["driver_name"] for s in first["suggested"]] == ["Driver 05"]
    assert first["review_status"] == "pending"  # Only a suggestion.
    assert len(first["incidents"]) == 1  # The wall and the car contact share a car.
    assert first["incidents"][0]["seconds"] == 20
    second = next(r for r in data["restarts"] if r["abandoned_attempt"] == 2)
    assert second["suggested"] == [] and second["incidents"] == []


def test_changed_confirmation_becomes_corrected(api, night):
    admin, round_ = night
    client = api(admin)
    restart = Restart.objects.get(abandoned_attempt__number=1)
    d5 = SeasonEntry.objects.get(driver__steam_guid=D5)
    d1 = SeasonEntry.objects.get(driver__steam_guid=D1)
    url = f"/restarts/{restart.id}/responsibility"
    body = {"responsibility": "drivers", "review_status": "confirmed", "reason": "Choque"}
    client.put(url, {**body, "driver_entry_ids": [d5.id]})
    restart.refresh_from_db()
    assert restart.review_status == "confirmed"
    client.put(url, {**body, "driver_entry_ids": [d1.id], "reason": "Video nuevo"})
    restart.refresh_from_db()
    assert restart.review_status == "corrected"
    summary = client.get(f"/rounds/{round_.id}/restarts").json()["summary"]
    assert summary["caused"][0]["driver_name"] == "Driver 01"  # A correction still counts.
    log = client.get("/audit").json()
    reviewed = [e for e in log if e["action"] == "restart.reviewed"]
    assert len(reviewed) == 2


def test_track_guidance_shows_in_the_briefing(api, night):
    admin, round_ = night
    client = api(admin)
    response = client.client.patch(
        f"/api/catalog/layouts/{round_.track_layout_id}/guidance",
        {"restart_guidance": "Reinicio si chocan antes de la curva 3", "first_lap_cutoff": "T3"},
        content_type="application/json",
    )
    assert response.status_code == 200
    briefing = client.get(f"/rounds/{round_.id}").json()["briefing"]
    assert briefing["restart_guidance"] == "Reinicio si chocan antes de la curva 3"
    assert briefing["first_lap_cutoff"] == "T3"
