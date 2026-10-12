from datetime import timedelta

import pytest
from django.utils import timezone

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.results.models import Penalty, RaceResult, ResultVersion
from apps.results.services import add_penalty


@pytest.fixture
def grid(season, car):
    return [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name),
            car=car,
            number=n,
        )
        for n, name in enumerate(["Ana", "Juan", "Martín", "Sofía"], start=1)
    ]


@pytest.fixture
def round_(season, layout):
    return Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-18T00:00Z"
    )


@pytest.fixture
def admin(api, champ_admin):
    return api(champ_admin)


def enter(client, round_, grid, order=(0, 1, 2, 3), reason=""):
    lines = [
        {"entry_id": grid[i].id, "status": "finished", "position": p}
        for p, i in enumerate(order, start=1)
    ]
    return client.put(f"/rounds/{round_.id}/result", {"lines": lines, "reason": reason})


def points(detail):
    return {line["driver_name"]: line["points"] for line in detail["result"]}


def test_result_goes_from_provisional_to_under_review_to_official(
    admin, api, driver_user, grid, round_
):
    first = enter(admin, round_, grid).json()
    assert first["status"] == "provisional"
    assert first["can_protest"] is True

    protest = api(driver_user).post(
        f"/rounds/{round_.id}/protests", {"description": "Juan me chocó en la T1"}
    )
    assert protest.json()["status"] == "under_review"

    blocked = admin.post(f"/rounds/{round_.id}/result/approve")
    assert blocked.json()["detail"] == "open_protests"

    protest_id = protest.json()["protests"][0]["id"]
    decided = admin.post(
        f"/protests/{protest_id}/decision", {"outcome": "dismissed", "decision": "Incidente"}
    )
    assert decided.json()["status"] == "provisional"

    official = admin.post(f"/rounds/{round_.id}/result/approve").json()
    assert official["status"] == "official"
    assert official["can_protest"] is False


def test_upheld_protest_adds_a_penalty_linked_to_the_attempt(admin, api, driver_user, grid, round_):
    enter(admin, round_, grid)
    protest_id = (
        api(driver_user)
        .post(f"/rounds/{round_.id}/protests", {"description": "x", "entry_ids": [grid[0].id]})
        .json()["protests"][0]["id"]
    )
    detail = admin.post(
        f"/protests/{protest_id}/decision",
        {
            "outcome": "upheld",
            "decision": "Ana empujó a Juan",
            "penalty": {"entry_id": grid[0].id, "kind": "positions", "value": 2},
        },
    ).json()
    penalty = detail["penalties"][0]
    assert penalty["attempt"] == 1
    assert penalty["protest_id"] == protest_id
    assert [line["driver_name"] for line in detail["result"]] == ["Juan", "Martín", "Ana", "Sofía"]


def test_correction_makes_a_new_version_and_keeps_the_old_one(admin, grid, round_):
    enter(admin, round_, grid)
    detail = enter(admin, round_, grid, order=(1, 0, 2, 3), reason="Orden mal cargado").json()
    assert detail["version"] == 2
    assert [v["kind"] for v in detail["versions"]] == ["correction", "entry"]
    assert detail["versions"][0]["reason"] == "Orden mal cargado"

    old = admin.get(f"/rounds/{round_.id}/result/versions/1").json()
    assert [line["driver_name"] for line in old] == ["Ana", "Juan", "Martín", "Sofía"]
    assert ResultVersion.objects.count() == 2


def test_correcting_an_official_result_needs_a_reason(admin, grid, round_):
    enter(admin, round_, grid)
    admin.post(f"/rounds/{round_.id}/result/approve")
    refused = enter(admin, round_, grid, order=(1, 0, 2, 3))
    assert refused.json()["detail"] == "reason_required"
    accepted = enter(admin, round_, grid, order=(1, 0, 2, 3), reason="Error de carga")
    assert accepted.json()["status"] == "official"
    assert accepted.json()["version"] == 2


def test_retroactive_penalty_updates_points_standings_and_career(admin, grid, round_):
    enter(admin, round_, grid)
    admin.post(f"/rounds/{round_.id}/result/approve")
    assert admin.get("/drivers").json()[0]["career_points"] == 25  # Ana

    detail = admin.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": grid[0].id, "kind": "positions", "value": 1, "reason": "Corte de pista"},
    ).json()
    assert points(detail) == {"Juan": 25, "Ana": 18, "Martín": 15, "Sofía": 12}
    assert detail["status"] == "official"

    standings = admin.get(f"/seasons/{round_.season_id}/standings").json()
    assert [(s["driver_name"], s["points"]) for s in standings[:2]] == [("Juan", 25), ("Ana", 18)]
    careers = {d["display_name"]: d["career_points"] for d in admin.get("/drivers").json()}
    assert (careers["Ana"], careers["Juan"]) == (18, 25)


def test_penalty_survives_a_later_correction_and_applies_once(admin, grid, round_):
    enter(admin, round_, grid)
    admin.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": grid[0].id, "kind": "points", "value": 5, "reason": "Conducta"},
    )
    detail = enter(admin, round_, grid, order=(1, 0, 2, 3), reason="Orden mal cargado").json()
    detail = enter(admin, round_, grid, order=(0, 1, 2, 3), reason="Volver al orden").json()
    assert points(detail)["Ana"] == 20
    assert detail["version"] == 4


def test_saving_the_same_lines_again_makes_no_new_version(admin, grid, round_):
    enter(admin, round_, grid)
    detail = enter(admin, round_, grid, reason="Mismo resultado").json()
    assert detail["version"] == 1


def test_same_imported_penalty_never_applies_twice(champ_admin, admin, grid, round_):
    enter(admin, round_, grid)
    result = RaceResult.objects.get()
    for _ in range(2):
        add_penalty(
            result,
            grid[1],
            "points",
            3,
            "Real Penalty: cut",
            champ_admin,
            source=Penalty.Source.IMPORTED,
            external_id="rp-42",
        )
    assert Penalty.objects.count() == 1
    assert points(admin.get(f"/rounds/{round_.id}").json())["Juan"] == 15


def test_dsq_penalty_gives_last_place_points(admin, grid, round_):
    enter(admin, round_, grid)
    detail = admin.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": grid[0].id, "kind": "dsq", "reason": "Peso ilegal"},
    ).json()
    assert points(detail)["Ana"] == 12  # Four starters, so the last position is 4th.
    assert points(detail)["Juan"] == 25


def test_protest_after_the_window_is_refused(admin, api, driver_user, grid, round_):
    enter(admin, round_, grid)
    RaceResult.objects.update(published_at=timezone.now() - timedelta(minutes=61))
    response = api(driver_user).post(f"/rounds/{round_.id}/protests", {"description": "tarde"})
    assert response.json()["detail"] == "protest_window_closed"


def test_admin_changes_the_protest_window(admin, api, driver_user, grid, round_, season):
    enter(admin, round_, grid)
    RaceResult.objects.update(published_at=timezone.now() - timedelta(minutes=61))
    admin.client.patch(
        f"/api/seasons/{season.id}/settings",
        {"protest_window_minutes": 120},
        content_type="application/json",
    )
    response = api(driver_user).post(f"/rounds/{round_.id}/protests", {"description": "a tiempo"})
    assert response.status_code == 200


def test_driver_cannot_add_penalties_or_approve(api, driver_user, admin, grid, round_):
    enter(admin, round_, grid)
    client = api(driver_user)
    assert client.post(f"/rounds/{round_.id}/result/approve").status_code == 403
    response = client.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": grid[0].id, "kind": "dsq", "reason": "x"},
    )
    assert response.status_code == 403


def test_penalty_needs_a_reason(admin, grid, round_):
    enter(admin, round_, grid)
    response = admin.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": grid[0].id, "kind": "dsq", "reason": "  "},
    )
    assert response.json()["detail"] == "reason_required"
