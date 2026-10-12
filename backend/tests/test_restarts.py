import pytest

from apps.audit.models import AuditEntry
from apps.competition.models import Attempt, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.results.models import ResultLine


@pytest.fixture
def grid(season, car):
    return [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name),
            car=car,
            number=n,
        )
        for n, name in enumerate(["Ana", "Juan", "Martín"], start=1)
    ]


@pytest.fixture
def round_(season, layout):
    return Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-18T00:00Z"
    )


def restart(client, round_, **fields):
    data = {"reason": "first_lap_crash", **fields}
    return client.post(f"/rounds/{round_.id}/restarts", data)


def test_two_restarts_and_a_final_race_give_three_attempts_and_one_points_award(
    api, champ_admin, grid, round_
):
    client = api(champ_admin)
    ana, juan, martin = grid
    first = restart(client, round_, lap=1, location="T2", explanation="Choque en la T2")
    assert first.status_code == 201
    restart(client, round_, reason="server_problem", responsibility="technical")
    client.put(
        f"/rounds/{round_.id}/result",
        {
            "lines": [
                {"entry_id": ana.id, "status": "finished", "position": 1},
                {"entry_id": juan.id, "status": "finished", "position": 2},
            ]
        },
    )

    data = client.get(f"/rounds/{round_.id}/restarts").json()
    assert [(a["number"], a["status"]) for a in data["attempts"]] == [
        (1, "abandoned"),
        (2, "abandoned"),
        (3, "accepted"),
    ]
    assert data["summary"]["total"] == 2
    assert Round.objects.count() == 1
    assert ResultLine.objects.filter(entry=ana).count() == 1
    assert client.get(f"/seasons/{round_.season_id}/standings").json()[0]["points"] == 25


def test_restart_stores_timing_location_reason_and_people(api, champ_admin, grid, round_):
    ana, juan, _ = grid
    response = restart(
        api(champ_admin),
        round_,
        lap=1,
        elapsed_seconds=42,
        location="Turn 2",
        explanation="Pile-up",
        requested_by_id=ana.driver_id,
        executed_by_id=juan.driver_id,
    )
    stored = response.json()["restarts"][0]
    assert stored["lap"] == 1
    assert stored["elapsed_seconds"] == 42
    assert stored["location"] == "Turn 2"
    assert stored["requested_by"] == "Ana"
    assert stored["executed_by"] == "Juan"
    assert stored["logged_by"] == "organizer"
    assert stored["review_status"] == "pending"


def test_requester_is_not_the_responsible_driver(api, champ_admin, grid, round_):
    ana, _, martin = grid
    response = restart(
        api(champ_admin),
        round_,
        requested_by_id=ana.driver_id,
        responsibility="drivers",
        driver_entry_ids=[martin.id],
    )
    stored = response.json()["restarts"][0]
    assert stored["requested_by"] == "Ana"
    assert [r["driver_name"] for r in stored["responsible"]] == ["Martín"]


def test_shared_responsibility_counts_once_in_the_total_and_once_per_driver(
    api, champ_admin, grid, round_
):
    _, juan, martin = grid
    client = api(champ_admin)
    restart(
        client,
        round_,
        responsibility="drivers",
        driver_entry_ids=[juan.id, martin.id],
        review_status="confirmed",
    )
    restart(
        client,
        round_,
        responsibility="drivers",
        driver_entry_ids=[martin.id],
        review_status="confirmed",
    )
    summary = client.get(f"/rounds/{round_.id}/restarts").json()["summary"]
    assert summary["total"] == 2
    assert summary["caused"] == [
        {"entry_id": martin.id, "driver_name": "Martín", "total": 2, "shared": 1},
        {"entry_id": juan.id, "driver_name": "Juan", "total": 1, "shared": 1},
    ]


def test_pending_technical_and_unknown_restarts_blame_no_driver(api, champ_admin, grid, round_):
    _, juan, _ = grid
    client = api(champ_admin)
    restart(client, round_, responsibility="drivers", driver_entry_ids=[juan.id])  # pending
    restart(client, round_, responsibility="technical", review_status="confirmed")
    restart(client, round_, responsibility="unknown", review_status="confirmed")
    summary = client.get(f"/rounds/{round_.id}/restarts").json()["summary"]
    assert summary["caused"] == []
    assert (summary["pending_or_disputed"], summary["technical"], summary["unknown"]) == (1, 1, 1)


def test_confirming_responsibility_updates_the_counts_and_the_audit(api, champ_admin, grid, round_):
    ana, *_ = grid
    client = api(champ_admin)
    restart_id = restart(client, round_).json()["restarts"][0]["id"]
    response = client.put(
        f"/restarts/{restart_id}/responsibility",
        {
            "responsibility": "drivers",
            "driver_entry_ids": [ana.id],
            "review_status": "confirmed",
            "reason": "Ana chocó primero",
        },
    )
    assert response.json()["summary"]["caused"][0]["driver_name"] == "Ana"
    entry = AuditEntry.objects.get(action="restart.reviewed")
    assert entry.reason == "Ana chocó primero"
    assert {"field": "responsible_drivers", "old": None, "new": "Ana"} in entry.changes


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"responsibility": "drivers"}, "drivers_required"),
        ({"responsibility": "technical", "driver_entry_ids": "ANY"}, "drivers_not_allowed"),
    ],
)
def test_responsibility_rules(api, champ_admin, grid, round_, fields, code):
    if fields.get("driver_entry_ids") == "ANY":
        fields["driver_entry_ids"] = [grid[0].id]
    response = restart(api(champ_admin), round_, **fields)
    assert response.status_code == 422
    assert response.json()["detail"] == code


def test_no_restart_after_the_race_is_accepted(api, champ_admin, grid, round_):
    client = api(champ_admin)
    client.put(
        f"/rounds/{round_.id}/result",
        {"lines": [{"entry_id": grid[0].id, "status": "finished", "position": 1}]},
    )
    response = restart(client, round_)
    assert response.status_code == 422
    assert response.json()["detail"] == "race_already_accepted"
    assert Attempt.objects.count() == 1


def test_late_restart_is_recorded_without_any_cutoff_check(api, champ_admin, grid, round_):
    response = restart(api(champ_admin), round_, lap=6, elapsed_seconds=900)
    assert response.status_code == 201


def test_driver_sees_restarts_but_cannot_record_one(api, driver_user, round_):
    client = api(driver_user)
    assert client.get(f"/rounds/{round_.id}/restarts").status_code == 200
    assert restart(client, round_).status_code == 403
