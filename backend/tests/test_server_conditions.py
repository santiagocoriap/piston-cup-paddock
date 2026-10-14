"""Phase 3: the real conditions of a round come from the server collector."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Track, TrackLayout
from apps.competition.models import Round


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season,
        number=1,
        track_layout=layout,
        scheduled_at=timezone.now(),
        announced_conditions={
            "time_of_day": "15:30",
            "weather": "Despejado",
            "air_temp_c": 28,
            "track_temp_c": 30,
            "grip": "89%",
        },
    )


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()["key"]


def session(minutes, kind, **data):
    when = (timezone.now() + timedelta(minutes=minutes)).isoformat()
    payload = {"type": kind, "track": "ks_highlands", "layout": "layout_long", **data}
    return {"kind": "session_started", "at": when, "data": payload}


def send(key, *items):
    batch = {"run_id": "run-1", "events": [{"seq": n, **item} for n, item in enumerate(items)]}
    Client().post(
        "/api/collector/events",
        batch,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )


def test_the_briefing_shows_what_the_server_used(api, champ_admin, key, round_):
    send(
        key,
        session(-60, 1, air_temp_c=15, road_temp_c=18, weather="1_heavy_fog"),
        session(
            -30,
            3,
            air_temp_c=20,
            road_temp_c=31,
            weather="3_clear",
            time_of_day="16:00",
            grip_pct=89,
        ),
    )
    briefing = api(champ_admin).get(f"/rounds/{round_.id}").json()["briefing"]
    real = briefing["server_conditions"]
    assert real["session_type"] == "race"  # The race wins over the practice.
    assert (real["weather"], real["air_temp_c"], real["track_temp_c"]) == ("3_clear", 20, 31)
    assert (real["time_of_day"], real["grip_pct"]) == ("16:00", 89)
    # 20 °C is far from the 28 °C announced. 31 °C, 16:00, and 89 % are close enough.
    assert briefing["conditions_differ"] == ["air_temp"]


def test_no_collector_data_means_no_server_conditions(api, champ_admin, round_):
    briefing = api(champ_admin).get(f"/rounds/{round_.id}").json()["briefing"]
    assert (briefing["server_conditions"], briefing["conditions_differ"]) == (None, [])
