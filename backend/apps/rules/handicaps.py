"""Ballast and restrictor. Pure functions with no database.

The rules come from docs/LEAGUE_RULES.md:
- Only a race win adds ballast and restrictor. The step depends on the number of season wins.
- A finish of 2nd or lower (also DNF and DSQ) removes one reduction step. Never below 0.
- A driver who does not start keeps the same values.
- The values have a maximum, and they start at 0 each season.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

LEAGUE_BALLAST_STEPS = (10, 10, 5, 3)
LEAGUE_RESTRICTOR_STEPS = (2, 2, 1)


class Outcome(StrEnum):
    WIN = "win"
    LOSS = "loss"  # A finish of 2nd or lower, a DNF, or a DSQ.
    ABSENT = "absent"  # DNS, or no line in the result.


@dataclass(frozen=True)
class HandicapRules:
    ballast_steps: Sequence[int] = LEAGUE_BALLAST_STEPS
    restrictor_steps: Sequence[int] = LEAGUE_RESTRICTOR_STEPS
    ballast_cap: int = 45
    restrictor_cap: int = 5
    ballast_reduction: int = 3
    restrictor_reduction: int = 1


@dataclass(frozen=True)
class Override:
    """An admin sets the values that a driver carries into one round.

    A persistent override changes the base for the next rounds. A temporary override is only
    for that round: the next rounds continue from the calculated value.
    """

    ballast_kg: int
    restrictor_pct: int
    persistent: bool


@dataclass
class Step:
    """One round for one driver: the values carried into the round, the result, and the
    values for the next round."""

    round_index: int
    before_kg: int
    before_pct: int
    outcome: Outcome
    season_wins: int
    change_kg: int
    change_pct: int
    capped: bool
    after_kg: int
    after_pct: int
    override: Override | None = None


@dataclass
class Progression:
    steps: list[Step] = field(default_factory=list)
    next_kg: int = 0
    next_pct: int = 0


def _step_value(steps: Sequence[int], win_number: int) -> int:
    """The increase for the given season win. The last step repeats."""
    if not steps:
        return 0
    return steps[min(win_number, len(steps)) - 1]


def progression(
    outcomes: Sequence[Outcome],
    rules: HandicapRules,
    overrides: dict[int, Override] | None = None,
) -> Progression:
    """Calculate the values of one driver over the rounds that have a result, in order.

    `outcomes` has one item for each round with a result. `overrides` maps a round index to an
    admin override of the values carried into that round.
    """
    overrides = overrides or {}
    result = Progression()
    kg = pct = wins = 0
    for index, outcome in enumerate(outcomes):
        override = overrides.get(index)
        calculated_kg, calculated_pct = kg, pct
        if override:
            kg, pct = override.ballast_kg, override.restrictor_pct
        before_kg, before_pct = kg, pct

        if outcome == Outcome.WIN:
            wins += 1
            add_kg = _step_value(rules.ballast_steps, wins)
            add_pct = _step_value(rules.restrictor_steps, wins)
        elif outcome == Outcome.LOSS:
            add_kg, add_pct = -rules.ballast_reduction, -rules.restrictor_reduction
        else:
            add_kg = add_pct = 0

        base_kg, base_pct = (
            (before_kg, before_pct)
            if not override or override.persistent
            else (calculated_kg, calculated_pct)
        )
        raw_kg, raw_pct = base_kg + add_kg, base_pct + add_pct
        after_kg = max(0, min(rules.ballast_cap, raw_kg))
        after_pct = max(0, min(rules.restrictor_cap, raw_pct))
        result.steps.append(
            Step(
                round_index=index,
                before_kg=before_kg,
                before_pct=before_pct,
                outcome=outcome,
                season_wins=wins,
                change_kg=after_kg - base_kg,
                change_pct=after_pct - base_pct,
                capped=raw_kg > rules.ballast_cap or raw_pct > rules.restrictor_cap,
                after_kg=after_kg,
                after_pct=after_pct,
                override=override,
            )
        )
        kg, pct = after_kg, after_pct
    result.next_kg, result.next_pct = kg, pct
    return result
