import pytest

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.rules.models import RulesVersion


@pytest.fixture
def grid(season, car):
    """Four entries: numbers 1 to 4."""
    return [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"Driver {n}"),
            car=car,
            number=n,
        )
        for n in range(1, 5)
    ]


@pytest.fixture
def rounds(season, layout):
    return [
        Round.objects.create(
            season=season, number=n, track_layout=layout, scheduled_at=f"2026-10-{10 + n}T00:00Z"
        )
        for n in (1, 2)
    ]


def line(entry, status="finished", position=None, **flags):
    return {"entry_id": entry.id, "status": status, "position": position, **flags}


def test_admin_enters_a_classification_with_dnf_dns_and_dsq(api, champ_admin, grid, rounds):
    a, b, c, d = grid
    response = api(champ_admin).put(
        f"/rounds/{rounds[0].id}/result",
        {
            "lines": [
                line(a, position=1),
                line(b, "dnf", 2),
                line(c, "dsq"),
                line(d, "dns"),
            ]
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert [(r["driver_name"], r["status"], r["position"], r["points"]) for r in result] == [
        ("Driver 1", "finished", 1, 25),
        ("Driver 2", "dnf", 2, 18),
        ("Driver 3", "dsq", None, 15),  # Three starters, so the last position is 3rd.
        ("Driver 4", "dns", None, 0),
    ]


def test_saving_again_replaces_the_result(api, champ_admin, grid, rounds):
    a, b, *_ = grid
    client = api(champ_admin)
    path = f"/rounds/{rounds[0].id}/result"
    client.put(path, {"lines": [line(a, position=1), line(b, position=2)]})
    response = client.put(path, {"lines": [line(b, position=1), line(a, position=2)]})
    assert [r["driver_name"] for r in response.json()["result"]] == ["Driver 2", "Driver 1"]


def test_invalid_positions_give_an_error_code(api, champ_admin, grid, rounds):
    a, b, *_ = grid
    response = api(champ_admin).put(
        f"/rounds/{rounds[0].id}/result", {"lines": [line(a, position=1), line(b, position=3)]}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "positions_not_continuous"


def test_entry_from_another_season_is_refused(api, champ_admin, grid, rounds, car, championship):
    other_season = championship.seasons.create(name="2027", planned_round_count=1)
    stranger = SeasonEntry.objects.create(
        season=other_season,
        driver=DriverProfile.objects.create(display_name="X"),
        car=car,
        number=1,
    )
    response = api(champ_admin).put(
        f"/rounds/{rounds[0].id}/result", {"lines": [line(stranger, position=1)]}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "entry_not_in_season"


def test_result_uses_the_bonuses_of_the_season_rules(api, champ_admin, season, grid, rounds):
    RulesVersion.objects.create(
        season=season, number=1, points_by_position=[10, 5], pole_bonus=1, fastest_lap_bonus=2
    )
    a, b, *_ = grid
    response = api(champ_admin).put(
        f"/rounds/{rounds[0].id}/result",
        {"lines": [line(a, position=1), line(b, position=2, pole=True, fastest_lap=True)]},
    )
    assert [r["points"] for r in response.json()["result"]] == [10, 8]
    assert response.json()["rules"]["version"] == 1


def test_new_season_starts_with_the_league_points(api, league_admin, championship):
    season = api(league_admin).post(
        f"/championships/{championship.id}/seasons", {"name": "2027", "planned_round_count": 2}
    )
    rules = RulesVersion.objects.get(season_id=season.json()["id"])
    assert rules.points_by_position == [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    assert (rules.pole_bonus, rules.fastest_lap_bonus) == (0, 0)


def test_standings_add_the_rounds_and_use_the_countback(api, champ_admin, grid, rounds):
    a, b, c, d = grid
    client = api(champ_admin)
    client.put(
        f"/rounds/{rounds[0].id}/result",
        {"lines": [line(a, position=1), line(b, position=2), line(c, position=3)]},
    )
    client.put(
        f"/rounds/{rounds[1].id}/result",
        {"lines": [line(b, position=1), line(a, position=2), line(c, position=3)]},
    )
    standings = client.get(f"/seasons/{grid[0].season_id}/standings").json()
    assert [(s["driver_name"], s["points"], s["rank"], s["wins"]) for s in standings] == [
        ("Driver 1", 43, 1, 1),
        ("Driver 2", 43, 1, 1),
        ("Driver 3", 30, 3, 0),
        ("Driver 4", 0, 4, 0),
    ]
    assert [(r["round_number"], r["position"]) for r in standings[0]["rounds"]] == [(1, 1), (2, 2)]


def test_driver_sees_the_standings_but_cannot_enter_results(api, driver_user, grid, rounds):
    client = api(driver_user)
    assert client.get(f"/seasons/{grid[0].season_id}/standings").status_code == 200
    assert client.get(f"/rounds/{rounds[0].id}").json()["can_manage"] is False
    response = client.put(f"/rounds/{rounds[0].id}/result", {"lines": []})
    assert response.status_code == 403


def test_user_outside_the_championship_cannot_see_the_round(api, make_user, rounds):
    outsider = api(make_user("outsider"))
    assert outsider.get(f"/rounds/{rounds[0].id}").status_code == 404
    assert outsider.get(f"/seasons/{rounds[0].season_id}/standings").status_code == 404
