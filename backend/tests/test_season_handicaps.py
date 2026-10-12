import pytest

from apps.competition.models import Round, SeasonEntry
from apps.handicaps.models import UsedHandicap
from apps.identity.models import DriverProfile


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
def rounds(season, layout):
    return [
        Round.objects.create(
            season=season, number=n, track_layout=layout, scheduled_at=f"2026-10-{10 + n}T00:00Z"
        )
        for n in (1, 2, 3, 4)
    ]


@pytest.fixture
def admin(api, champ_admin):
    return api(champ_admin)


def race(client, round_, order, reason=""):
    lines = [
        {"entry_id": entry.id, "status": "finished", "position": p}
        for p, entry in enumerate(order, start=1)
    ]
    response = client.put(f"/rounds/{round_.id}/result", {"lines": lines, "reason": reason})
    assert response.status_code == 200, response.json()


def handicaps(client, season):
    data = client.get(f"/seasons/{season.id}/handicaps").json()
    return data, {e["driver_name"]: e for e in data["entries"]}


def test_next_round_values_follow_the_league_rules(admin, season, grid, rounds):
    ana, juan, martin = grid
    race(admin, rounds[0], [ana, juan, martin])
    race(admin, rounds[1], [ana, juan, martin])
    race(admin, rounds[2], [juan, ana, martin])
    data, by_name = handicaps(admin, season)
    assert data["next_round_number"] == 4
    assert (by_name["Ana"]["next_kg"], by_name["Ana"]["next_pct"]) == (17, 3)
    assert (by_name["Juan"]["next_kg"], by_name["Juan"]["next_pct"]) == (10, 2)
    assert (by_name["Martín"]["next_kg"], by_name["Martín"]["next_pct"]) == (0, 0)


def test_each_step_explains_the_change(admin, season, grid, rounds):
    ana, juan, _ = grid
    race(admin, rounds[0], [ana, juan])
    race(admin, rounds[1], [juan, ana])
    _, by_name = handicaps(admin, season)
    step = by_name["Ana"]["rounds"][1]
    assert (step["before_kg"], step["outcome"], step["change_kg"], step["after_kg"]) == (
        10,
        "loss",
        -3,
        7,
    )
    assert (step["position"], step["season_wins"]) == (2, 1)


def test_driver_without_a_line_keeps_the_values(admin, season, grid, rounds):
    ana, juan, _ = grid
    race(admin, rounds[0], [ana, juan])
    race(admin, rounds[1], [juan])  # Ana did not take part.
    _, by_name = handicaps(admin, season)
    assert by_name["Ana"]["rounds"][1]["outcome"] == "absent"
    assert by_name["Ana"]["next_kg"] == 10


def test_correction_changes_the_next_values_but_not_the_used_values(admin, season, grid, rounds):
    ana, juan, _ = grid
    race(admin, rounds[0], [ana, juan])
    race(admin, rounds[1], [ana, juan])
    used = UsedHandicap.objects.get(round=rounds[1], entry=ana)
    assert (used.ballast_kg, used.restrictor_pct) == (10, 2)

    race(admin, rounds[0], [juan, ana], reason="Ana tenía una sanción")
    _, by_name = handicaps(admin, season)
    round_2 = by_name["Ana"]["rounds"][1]
    assert (round_2["used_kg"], round_2["before_kg"]) == (10, 0)
    assert by_name["Ana"]["next_kg"] == 10
    used.refresh_from_db()
    assert used.ballast_kg == 10


def test_admin_adjusts_the_next_round_with_a_reason(admin, season, grid, rounds):
    ana, juan, _ = grid
    race(admin, rounds[0], [ana, juan])
    response = admin.post(
        f"/seasons/{season.id}/handicaps/adjustments",
        {
            "entry_id": ana.id,
            "round_id": rounds[1].id,
            "ballast_kg": 5,
            "restrictor_pct": 0,
            "mode": "temporary",
            "reason": "Problema con el auto",
        },
    )
    by_name = {e["driver_name"]: e for e in response.json()["entries"]}
    assert (by_name["Ana"]["next_kg"], by_name["Ana"]["next_adjustment_reason"]) == (
        5,
        "Problema con el auto",
    )


def test_temporary_adjustment_does_not_change_later_rounds(admin, season, grid, rounds):
    ana, juan, _ = grid
    race(admin, rounds[0], [ana, juan])
    admin.post(
        f"/seasons/{season.id}/handicaps/adjustments",
        {
            "entry_id": ana.id,
            "round_id": rounds[1].id,
            "ballast_kg": 0,
            "restrictor_pct": 0,
            "mode": "temporary",
            "reason": "Prueba",
        },
    )
    race(admin, rounds[1], [juan, ana])
    _, by_name = handicaps(admin, season)
    assert by_name["Ana"]["rounds"][1]["before_kg"] == 0
    assert by_name["Ana"]["next_kg"] == 7  # 10 calculated, minus 3.


@pytest.mark.parametrize(
    ("change", "code"),
    [({"reason": " "}, "reason_required"), ({"ballast_kg": 50}, "above_cap")],
)
def test_adjustment_rules(admin, season, grid, rounds, change, code):
    data = {
        "entry_id": grid[0].id,
        "round_id": rounds[0].id,
        "ballast_kg": 5,
        "restrictor_pct": 0,
        "mode": "persistent",
        "reason": "x",
        **change,
    }
    response = admin.post(f"/seasons/{season.id}/handicaps/adjustments", data)
    assert response.json()["detail"] == code


def test_driver_sees_but_cannot_adjust(api, driver_user, season, grid, rounds):
    client = api(driver_user)
    assert client.get(f"/seasons/{season.id}/handicaps").json()["can_manage"] is False
    response = client.post(
        f"/seasons/{season.id}/handicaps/adjustments",
        {
            "entry_id": grid[0].id,
            "round_id": rounds[0].id,
            "ballast_kg": 0,
            "restrictor_pct": 0,
            "mode": "temporary",
            "reason": "x",
        },
    )
    assert response.status_code == 403
