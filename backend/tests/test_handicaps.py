"""Ballast and restrictor rules from docs/LEAGUE_RULES.md."""

from apps.rules.handicaps import HandicapRules, Outcome, Override, progression

RULES = HandicapRules()
W, L, A = Outcome.WIN, Outcome.LOSS, Outcome.ABSENT


def values(outcomes, overrides=None):
    result = progression(outcomes, RULES, overrides)
    return [(s.after_kg, s.after_pct) for s in result.steps]


def test_wins_add_the_league_steps():
    assert values([W, W, W, W]) == [(10, 2), (20, 4), (25, 5), (28, 5)]


def test_the_table_from_the_league_rules():
    after = values([W] * 10)
    assert [after[i] for i in (0, 1, 2, 3, 7, 8, 9)] == [
        (10, 2),
        (20, 4),
        (25, 5),
        (28, 5),
        (40, 5),
        (43, 5),
        (45, 5),
    ]


def test_second_place_removes_3_kg_and_1_percent():
    assert values([W, W, W, L]) == [(10, 2), (20, 4), (25, 5), (22, 4)]


def test_removal_does_not_change_the_win_count():
    # 3 wins (25 kg), then 2nd (22 kg), then the 4th season win adds 3 kg.
    assert values([W, W, W, L, W])[-1] == (25, 5)


def test_absent_driver_keeps_the_values():
    assert values([W, A, A]) == [(10, 2), (10, 2), (10, 2)]


def test_values_never_go_below_zero():
    assert values([L, W, L, L, L, L]) == [(0, 0), (10, 2), (7, 1), (4, 0), (1, 0), (0, 0)]


def test_each_step_explains_the_change():
    step = progression([W, W, W, W, W, W, W, W, W, W], RULES).steps[9]
    assert (step.before_kg, step.change_kg, step.after_kg) == (43, 2, 45)
    assert step.season_wins == 10
    assert step.capped is True


def test_next_round_values_come_from_the_last_result():
    result = progression([W, L], RULES)
    assert (result.next_kg, result.next_pct) == (7, 1)


def test_persistent_override_changes_the_base_for_later_rounds():
    after = values([W, L, L], {1: Override(0, 0, persistent=True)})
    assert after == [(10, 2), (0, 0), (0, 0)]


def test_temporary_override_is_only_for_one_round():
    result = progression([W, L, L], RULES, {1: Override(0, 0, persistent=False)})
    assert (result.steps[1].before_kg, result.steps[1].after_kg) == (0, 7)
    assert result.steps[2].after_kg == 4


def test_a_corrected_result_changes_the_later_values():
    before = progression([W, W], RULES)
    after = progression([L, W], RULES)  # Round 1 corrected: no win.
    assert (before.next_kg, after.next_kg) == (20, 10)
