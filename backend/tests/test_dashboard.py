import pytest

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def me(make_user, championship):
    user = make_user("ana")
    ChampionshipMember.objects.create(
        championship=championship, user=user, role=ChampionshipMember.Role.DRIVER
    )
    return user


@pytest.fixture
def grid(season, car, me):
    ana = SeasonEntry.objects.create(
        season=season,
        driver=DriverProfile.objects.create(display_name="Ana", user=me),
        car=car,
        number=7,
    )
    juan = SeasonEntry.objects.create(
        season=season, driver=DriverProfile.objects.create(display_name="Juan"), car=car, number=8
    )
    return ana, juan


@pytest.fixture
def rounds(season, layout):
    return [
        Round.objects.create(
            season=season,
            number=n,
            track_layout=layout,
            scheduled_at=f"2026-10-{10 + n}T23:30Z",
        )
        for n in (1, 2, 3)
    ]


def race(client, round_, order):
    lines = [
        {"entry_id": e.id, "status": "finished", "position": p} for p, e in enumerate(order, 1)
    ]
    client.put(f"/rounds/{round_.id}/result", {"lines": lines})


def test_dashboard_shows_position_points_recent_results_and_next_round(
    api, champ_admin, me, grid, rounds
):
    admin = api(champ_admin)
    ana, juan = grid
    race(admin, rounds[0], [ana, juan])
    race(admin, rounds[1], [juan, ana])

    card = api(me).get("/dashboard").json()["seasons"][0]
    assert (card["rank"], card["points"], card["wins"], card["entries"]) == (1, 43, 1, 2)
    assert (card["entry_number"], card["car_name"]) == (7, "Acura ARX-06")
    assert [(r["round_number"], r["position"], r["points"]) for r in card["recent"]] == [
        (2, 2, 18),
        (1, 1, 25),
    ]
    next_round = card["next_round"]
    assert (next_round["round_number"], next_round["track_name"]) == (3, "Highlands")
    assert (next_round["ballast_kg"], next_round["restrictor_pct"]) == (7, 1)


def test_user_without_a_driver_profile_sees_an_empty_dashboard(api, champ_admin):
    data = api(champ_admin).get("/dashboard").json()
    assert data == {"has_driver_profile": False, "seasons": []}


def test_briefing_shows_conditions_protest_window_and_my_handicap(
    api, champ_admin, me, grid, rounds
):
    admin = api(champ_admin)
    ana, juan = grid
    race(admin, rounds[0], [ana, juan])
    conditions = {
        "time_of_day": "14:00",
        "weather": "Nublado",
        "air_temp_c": 18,
        "track_temp_c": 24,
        "grip": "Optimum",
        "notes": "",
    }
    admin.client.patch(
        f"/api/rounds/{rounds[1].id}/calendar",
        {"announced_conditions": conditions},
        content_type="application/json",
    )
    briefing = api(me).get(f"/rounds/{rounds[1].id}").json()["briefing"]
    assert briefing["announced_conditions"] == conditions
    assert briefing["protest_window_minutes"] == 60
    assert briefing["my_handicap"] == {
        "entry_number": 7,
        "car_name": "Acura ARX-06",
        "ballast_kg": 10,
        "restrictor_pct": 2,
        "source": "assigned",
    }


def test_briefing_of_a_past_race_shows_the_used_values(api, champ_admin, me, grid, rounds):
    admin = api(champ_admin)
    ana, juan = grid
    race(admin, rounds[0], [ana, juan])
    race(admin, rounds[1], [juan, ana])
    mine = api(me).get(f"/rounds/{rounds[1].id}").json()["briefing"]["my_handicap"]
    assert (mine["ballast_kg"], mine["source"]) == (10, "used")


def test_briefing_has_no_handicap_for_a_user_who_does_not_race(api, champ_admin, rounds):
    briefing = api(champ_admin).get(f"/rounds/{rounds[0].id}").json()["briefing"]
    assert briefing["my_handicap"] is None
