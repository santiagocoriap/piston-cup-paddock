"""Title scenarios with the standings rules: points, then countback of finishes."""

from collections import Counter

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.rules.scoring import PointsRules
from apps.rules.title import Contender, scenarios

RULES = PointsRules(points_by_position=(25, 18, 15), pole_bonus=1, fastest_lap_bonus=1)


def driver(entry_id, points, *positions):
    return Contender(entry_id, points, Counter(positions))


def by_id(result):
    return {d.entry_id: d for d in result.drivers}


def test_leader_is_champion_when_no_rival_can_reach():
    result = scenarios([driver(1, 100, 1, 1, 1, 1), driver(2, 70, 2, 2, 2, 2)], RULES, 1)
    assert result.max_per_round == 27
    assert by_id(result)[1].status == "champion"
    assert by_id(result)[2].status == "eliminated"
    assert result.leader_target is None


def test_equal_points_go_to_countback():
    # Driver 2 can reach 100 with one more win, but driver 1 has more wins after that too.
    result = scenarios([driver(1, 100, 1, 1, 1), driver(2, 73, 1, 2, 2)], RULES, 1)
    assert by_id(result)[1].status == "champion"
    # Here both have one win after the last round, and driver 2 has more 2nd places.
    result = scenarios([driver(1, 100, 1, 3, 3), driver(2, 73, 2, 2, 2)], RULES, 1)
    assert by_id(result)[2].status == "contender"


def test_contender_depends_on_rivals_and_target_is_possible():
    drivers = [driver(1, 50, 1, 1), driver(2, 40, 2, 1), driver(3, 30, 2, 2)]
    result = scenarios(drivers, RULES, 2)
    status = by_id(result)
    assert [status[i].status for i in (1, 2, 3)] == ["contender"] * 3
    # Leader wins both: 104. Rival 2 is 2nd both: 40 + 38 = 78. Rival 3: 68.
    assert status[1].own_destiny is True
    # Driver 3 wins both: 84. The leader is 2nd both: 50 + 38 = 88. So 3 needs help.
    assert status[3].own_destiny is False
    # Rival best: 40 + 54 = 94. The leader needs 45, and 2 wins give 54, so it shows.
    assert result.leader_target == 45
    assert result.leader_target <= result.remaining_rounds * result.max_per_round


def test_target_never_shows_when_it_is_not_possible():
    drivers = [driver(1, 50, 1, 1), driver(2, 49, 2, 1)]
    result = scenarios(drivers, RULES, 1)
    # Rival best: 49 + 27 = 76. The leader needs 27 of a maximum of 27: possible.
    assert result.leader_target == 27
    drivers = [driver(1, 50, 1, 1), driver(2, 50, 1, 2)]
    result = scenarios(drivers, RULES, 1)
    # Rival best 77. The leader needs 28, more than 27, so no target.
    assert result.leader_target is None


def test_api_shows_limits_and_counts(api, champ_admin, season, layout, car):
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
        )
        for n in (1, 2)
    ]
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    admin = api(champ_admin)
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
    data = admin.get(f"/seasons/{season.id}/title").json()
    assert (data["planned_rounds"], data["rounds_with_result"], data["remaining_rounds"]) == (
        8,
        1,
        7,
    )
    assert data["leader_id"] == entries[0].id
    assert "provisional_results" in data["limits"]
    assert {d["status"] for d in data["drivers"]} == {"contender"}
