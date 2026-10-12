from apps.voting.tally import decide


def test_the_options_with_the_most_votes_win():
    outcome = decide({1: 5, 2: 3, 3: 1}, slots=2)
    assert (outcome.winners, outcome.tied) == ([1, 2], [])


def test_fewer_options_than_slots_all_win():
    assert decide({1: 0, 2: 4}, slots=3).winners == [2, 1]


def test_a_tie_inside_the_winners_needs_no_runoff():
    assert decide({1: 4, 2: 4, 3: 1}, slots=2).winners == [1, 2]


def test_three_options_tied_for_the_last_two_slots_go_to_a_runoff():
    outcome = decide({1: 9, 2: 4, 3: 4, 4: 4, 5: 1}, slots=3)
    assert outcome.winners == [1]
    assert sorted(outcome.tied) == [2, 3, 4]
    assert outcome.open_slots == 2


def test_tie_for_the_only_slot():
    outcome = decide({1: 2, 2: 2}, slots=1)
    assert (outcome.winners, sorted(outcome.tied), outcome.open_slots) == ([], [1, 2], 1)
