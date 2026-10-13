"""Conditions draw: a pool for each season, a draw into the briefing, and redraws with reason."""

import pytest

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile

POOL = {
    "weather": ["Despejado", " Nublado ", ""],
    "time_of_day": ["13:00"],
    "grip": ["Rápido"],
    "air_temp_min": 18,
    "air_temp_max": 26,
}


@pytest.fixture
def round_(season, layout):
    return Round.objects.create(
        season=season, number=1, track_layout=layout, announced_conditions={"notes": "Sin pits"}
    )


def test_pool_and_draw_into_the_briefing(api, champ_admin, season, round_):
    client = api(champ_admin)
    pool = client.put(f"/seasons/{season.id}/conditions-pool", POOL).json()
    assert pool["weather"] == ["Despejado", "Nublado"]  # Trimmed, empty values out.
    draws = client.post(f"/rounds/{round_.id}/draw-conditions", {}).json()
    values = draws[0]["values"]
    assert values["weather"] in ("Despejado", "Nublado")
    assert values["time_of_day"] == "13:00"
    assert 18 <= values["air_temp_c"] <= 26
    assert values["track_temp_c"] is None  # No range in the pool.
    briefing = client.get(f"/rounds/{round_.id}").json()["briefing"]["announced_conditions"]
    assert briefing["notes"] == "Sin pits" and briefing["grip"] == "Rápido"


def test_redraw_needs_a_reason_and_keeps_the_history(api, champ_admin, season, round_):
    client = api(champ_admin)
    client.put(f"/seasons/{season.id}/conditions-pool", POOL)
    client.post(f"/rounds/{round_.id}/draw-conditions", {})
    refused = client.post(f"/rounds/{round_.id}/draw-conditions", {})
    assert refused.json()["detail"] == "reason_required"
    draws = client.post(
        f"/rounds/{round_.id}/draw-conditions", {"reason": "Lluvia no corresponde"}
    ).json()
    assert len(draws) == 2 and draws[1]["reason"] == "Lluvia no corresponde"


def test_empty_pool_and_round_with_result(api, champ_admin, season, round_, car):
    client = api(champ_admin)
    assert client.post(f"/rounds/{round_.id}/draw-conditions", {}).json()["detail"] == "pool_empty"
    client.put(f"/seasons/{season.id}/conditions-pool", POOL)
    entry = SeasonEntry.objects.create(
        season=season, driver=DriverProfile.objects.create(display_name="D"), car=car, number=1
    )
    client.put(
        f"/rounds/{round_.id}/result",
        {"lines": [{"entry_id": entry.id, "status": "finished", "position": 1}]},
    )
    response = client.post(f"/rounds/{round_.id}/draw-conditions", {})
    assert response.json()["detail"] == "round_has_result"


def test_driver_cannot_draw(api, driver_user, round_):
    assert api(driver_user).post(f"/rounds/{round_.id}/draw-conditions", {}).status_code == 403
