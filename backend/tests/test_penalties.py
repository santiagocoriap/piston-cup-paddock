"""Penalties change the classification and the points from the entered result."""

from apps.rules.scoring import (
    LEAGUE_POINTS,
    Line,
    PenaltyKind,
    PenaltyRule,
    PointsRules,
    Status,
    penalized_points,
)

RULES = PointsRules(LEAGUE_POINTS)
RESULT = [Line(i, Status.FINISHED, i) for i in range(1, 5)] + [Line(5, Status.DNF, 5)]


def positions(lines):
    return {line.entry_id: (line.status, line.position) for line in lines}


def test_no_penalty_keeps_the_result():
    final, points = penalized_points(RESULT, [], RULES)
    assert positions(final) == positions(RESULT)
    assert points == {1: 25, 2: 18, 3: 15, 4: 12, 5: 10}


def test_position_penalty_moves_the_driver_down_and_the_others_up():
    final, points = penalized_points(RESULT, [PenaltyRule(2, PenaltyKind.POSITIONS, 2)], RULES)
    assert [e for e, _ in sorted(positions(final).items(), key=lambda x: x[1][1])] == [
        1,
        3,
        4,
        2,
        5,
    ]
    assert (points[2], points[3], points[4]) == (12, 18, 15)


def test_position_penalty_stops_at_the_last_classified_place():
    final, _ = penalized_points(RESULT, [PenaltyRule(1, PenaltyKind.POSITIONS, 10)], RULES)
    assert positions(final)[1] == (Status.FINISHED, 5)
    assert positions(final)[5] == (Status.DNF, 4)


def test_dsq_penalty_removes_the_driver_and_gives_last_place_points():
    final, points = penalized_points(RESULT, [PenaltyRule(1, PenaltyKind.DSQ)], RULES)
    assert positions(final)[1] == (Status.DSQ, None)
    assert positions(final)[2] == (Status.FINISHED, 1)
    assert points[1] == 10  # Five starters, so the last position is 5th.
    assert points[2] == 25


def test_points_penalty_keeps_the_position():
    final, points = penalized_points(RESULT, [PenaltyRule(1, PenaltyKind.POINTS, 5)], RULES)
    assert positions(final)[1] == (Status.FINISHED, 1)
    assert points[1] == 20


def test_the_same_penalties_always_give_the_same_result():
    penalties = [PenaltyRule(2, PenaltyKind.POSITIONS, 1)]
    once, _ = penalized_points(RESULT, penalties, RULES)
    again, _ = penalized_points(RESULT, penalties, RULES)
    assert positions(once) == positions(again)


def test_penalty_for_a_driver_without_a_position_changes_nothing():
    lines = [Line(1, Status.FINISHED, 1), Line(2, Status.DNS, None)]
    final, points = penalized_points(lines, [PenaltyRule(2, PenaltyKind.POSITIONS, 3)], RULES)
    assert positions(final) == positions(lines)
    assert points == {1: 25, 2: 0}
