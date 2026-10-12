"""Count a ballot. Pure functions with no database."""

from dataclasses import dataclass, field


@dataclass
class Outcome:
    winners: list[int] = field(default_factory=list)  # Option IDs that win.
    tied: list[int] = field(default_factory=list)  # Option IDs tied for the open slots.
    open_slots: int = 0  # The slots that the tied options compete for.


def decide(totals: dict[int, int], slots: int) -> Outcome:
    """Pick the options with the most votes. A tie at the cut gives a runoff instead."""
    ranked = sorted(totals, key=lambda option: -totals[option])
    if len(ranked) <= slots:
        return Outcome(winners=ranked)
    cut = totals[ranked[slots - 1]]
    above = [o for o in ranked if totals[o] > cut]
    at_cut = [o for o in ranked if totals[o] == cut]
    open_slots = slots - len(above)
    if len(at_cut) == open_slots:
        return Outcome(winners=above + at_cut)
    return Outcome(winners=above, tied=at_cut, open_slots=open_slots)
