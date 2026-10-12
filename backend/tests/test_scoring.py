"""The points and tiebreaker rules from docs/LEAGUE_RULES.md (ticket #2)."""

import pytest

from apps.rules.scoring import (
    LEAGUE_POINTS,
    Line,
    PointsRules,
    ResultError,
    Status,
    race_points,
    standings,
    validate,
)

RULES = PointsRules(points_by_position=LEAGUE_POINTS)


def finished(entry_id, position, **flags):
    return Line(entry_id, Status.FINISHED, position, **flags)


def dnf(entry_id, position, **flags):
    return Line(entry_id, Status.DNF, position, **flags)


class TestRacePoints:
    def test_league_table_gives_25_to_1_for_the_top_ten(self):
        lines = [finished(i, i) for i in range(1, 13)]
        points = race_points(lines, RULES)
        assert [points[i] for i in range(1, 13)] == [25, 18, 15, 12, 10, 8, 6, 4, 2, 1, 0, 0]

    def test_dnf_gets_the_points_of_its_classified_position(self):
        points = race_points([finished(1, 1), finished(2, 2), dnf(3, 3)], RULES)
        assert points[3] == 15

    def test_dns_gets_zero(self):
        points = race_points([finished(1, 1), Line(2, Status.DNS, None)], RULES)
        assert points[2] == 0

    def test_dsq_gets_the_points_of_the_last_position_of_the_race(self):
        # Four starters: three classified and one DSQ. The last position is 4th.
        lines = [finished(1, 1), finished(2, 2), finished(3, 3), Line(4, Status.DSQ, None)]
        assert race_points(lines, RULES)[4] == 12

    def test_dsq_in_a_full_grid_gets_zero(self):
        lines = [finished(i, i) for i in range(1, 12)] + [Line(12, Status.DSQ, None)]
        assert race_points(lines, RULES)[12] == 0

    def test_league_rules_give_no_bonus(self):
        lines = [finished(1, 1), finished(2, 2, pole=True, fastest_lap=True)]
        assert race_points(lines, RULES)[2] == 18

    def test_configured_bonuses_are_added(self):
        rules = PointsRules(LEAGUE_POINTS, pole_bonus=1, fastest_lap_bonus=2)
        lines = [finished(1, 1), finished(2, 2, pole=True, fastest_lap=True)]
        assert race_points(lines, rules)[2] == 21

    def test_dsq_loses_its_bonuses(self):
        rules = PointsRules((25, 18), pole_bonus=1, fastest_lap_bonus=2)
        lines = [finished(1, 1), Line(2, Status.DSQ, None, pole=True, fastest_lap=True)]
        assert race_points(lines, rules)[2] == 18


class TestValidate:
    def test_valid_result_has_no_errors(self):
        validate([finished(1, 1), dnf(2, 2), Line(3, Status.DNS, None)])

    @pytest.mark.parametrize(
        ("lines", "code"),
        [
            ([finished(1, 1), finished(2, 3)], "positions_not_continuous"),
            ([finished(1, 1), finished(2, 1)], "positions_not_continuous"),
            ([finished(1, None)], "position_required"),
            ([Line(1, Status.DNS, 1)], "position_not_allowed"),
            ([Line(1, Status.DSQ, 1)], "position_not_allowed"),
            ([finished(1, 1), finished(1, 2)], "duplicate_entry"),
            ([finished(1, 1, pole=True), finished(2, 2, pole=True)], "one_pole_only"),
            ([finished(1, 1), dnf(2, 2, fastest_lap=True)], None),
            ([Line(1, Status.DNS, None, fastest_lap=True)], "dns_has_no_bonus"),
        ],
    )
    def test_invalid_results(self, lines, code):
        if code is None:
            validate(lines)
            return
        with pytest.raises(ResultError) as error:
            validate(lines)
        assert error.value.code == code


class TestStandings:
    def test_points_add_up_over_the_season(self):
        races = [
            [finished(1, 1), finished(2, 2)],
            [finished(2, 1), finished(1, 2)],
            [finished(1, 1), finished(2, 2)],
        ]
        table = standings([1, 2], [(r, race_points(r, RULES)) for r in races])
        assert [(row.entry_id, row.points, row.rank) for row in table] == [(1, 68, 1), (2, 61, 2)]

    def test_equal_points_go_to_the_driver_with_more_wins(self):
        # Driver 1: 25 + 0 = 25. Driver 2: 15 + 10 = 25. Driver 1 has a win.
        races = [
            [finished(1, 1), finished(3, 2), finished(2, 3)],
            [finished(3, 1), finished(4, 2), finished(5, 3), finished(6, 4), finished(2, 5)],
        ]
        table = standings([1, 2, 3, 4, 5, 6], [(r, race_points(r, RULES)) for r in races])
        ranks = {row.entry_id: row.rank for row in table}
        assert ranks[1] < ranks[2]

    def test_equal_points_and_wins_go_to_the_driver_with_more_second_places(self):
        rules = PointsRules((10, 6, 4, 3))
        a, b, c, d = 1, 2, 3, 4
        races = [
            [finished(a, 1), finished(c, 2), finished(b, 3)],
            [finished(b, 1), finished(a, 2), finished(c, 3)],
            [finished(c, 1), finished(a, 2), finished(b, 3)],
            [finished(c, 1), finished(d, 2), finished(b, 3)],
        ]
        # A: 10 + 6 + 6 = 22, one win, two 2nd places.
        # B: 4 + 10 + 4 + 4 = 22, one win, no 2nd place.
        table = standings([a, b, c, d], [(r, race_points(r, rules)) for r in races])
        assert [(row.entry_id, row.points, row.rank) for row in table] == [
            (c, 30, 1),
            (a, 22, 2),
            (b, 22, 3),
            (d, 6, 4),
        ]

    def test_full_equality_shares_the_position(self):
        races = [[finished(1, 1), finished(2, 2)], [finished(2, 1), finished(1, 2)]]
        table = standings([1, 2, 3], [(r, race_points(r, RULES)) for r in races])
        assert [(row.entry_id, row.rank) for row in table] == [(1, 1), (2, 1), (3, 3)]

    def test_entry_without_races_has_zero_points(self):
        table = standings([1, 2], [([finished(1, 1)], {1: 25})])
        assert table[1].entry_id == 2
        assert table[1].points == 0

    def test_dnf_position_counts_for_countback_and_dsq_does_not(self):
        races = [[dnf(1, 1), Line(2, Status.DSQ, None)]]
        table = standings([1, 2], [(r, race_points(r, PointsRules((25, 25)))) for r in races])
        assert [(row.entry_id, row.wins) for row in table] == [(1, 1), (2, 0)]
