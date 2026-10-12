"""Title scenarios. Pure functions with no database.

The math uses the standings rules: points first, then the count of wins, 2nd places, and so on.
A future round can give at most the points of 1st place plus the pole and fastest-lap bonuses.
"""

from collections import Counter
from dataclasses import dataclass, field

from .scoring import PointsRules


@dataclass
class Contender:
    entry_id: int
    points: int
    finishes: Counter  # Position -> count, for classified finishes.


@dataclass
class DriverStatus:
    entry_id: int
    points: int
    best_case: int  # The points if the driver wins every remaining round with both bonuses.
    status: str  # "champion", "contender", or "eliminated"
    own_destiny: bool  # The driver wins the title if they win every round with both bonuses.


@dataclass
class TitleScenarios:
    remaining_rounds: int
    max_per_round: int
    max_if_not_winner: int
    drivers: list[DriverStatus] = field(default_factory=list)
    # The leader is sure of the title with this many points or more, whatever the rivals do.
    # None when no possible points total is sure. Then the title depends on rival results.
    leader_target: int | None = None
    leader_id: int | None = None


def _countback(finishes: Counter, depth: int) -> tuple:
    return tuple(finishes[p] for p in range(1, depth + 1))


def _beats(a: Contender, a_extra: Counter, b: Contender, b_extra: Counter, depth: int) -> int:
    """1 if a ranks above b, 0 if they share the rank, -1 if b ranks above a."""
    a_key = (a.points, *_countback(a.finishes + a_extra, depth))
    b_key = (b.points, *_countback(b.finishes + b_extra, depth))
    return (a_key > b_key) - (a_key < b_key)


def scenarios(drivers: list[Contender], rules: PointsRules, remaining: int) -> TitleScenarios:
    points = rules.points_by_position
    bonus = rules.pole_bonus + rules.fastest_lap_bonus
    top = (points[0] if points else 0) + bonus
    second = (points[1] if len(points) > 1 else 0) + bonus
    result = TitleScenarios(remaining, top, second)
    if not drivers:
        return result
    depth = max([len(points), *(max(d.finishes, default=0) for d in drivers)])
    leader = max(drivers, key=lambda d: (d.points, *_countback(d.finishes, depth)))
    result.leader_id = leader.entry_id

    def can_catch(rival: Contender, target: Contender) -> bool:
        """The rival wins every round with both bonuses, and the target scores nothing."""
        best = Contender(rival.entry_id, rival.points + remaining * top, rival.finishes)
        return _beats(best, Counter({1: remaining}), target, Counter(), depth) >= 0

    def own_destiny(driver: Contender) -> bool:
        """The driver wins every round with both bonuses. Each rival is 2nd every round with both
        bonuses, which is the most a rival can get when the driver wins."""
        mine = Contender(driver.entry_id, driver.points + remaining * top, driver.finishes)
        for rival in drivers:
            if rival.entry_id == driver.entry_id:
                continue
            theirs = Contender(rival.entry_id, rival.points + remaining * second, rival.finishes)
            if _beats(mine, Counter({1: remaining}), theirs, Counter({2: remaining}), depth) <= 0:
                return False
        return True

    leader_sure = all(
        not can_catch(rival, leader) for rival in drivers if rival.entry_id != leader.entry_id
    )
    for driver in drivers:
        best_case = driver.points + remaining * top
        if driver.entry_id == leader.entry_id:
            status = "champion" if leader_sure else "contender"
        else:
            status = "contender" if can_catch(driver, leader) else "eliminated"
        result.drivers.append(
            DriverStatus(
                entry_id=driver.entry_id,
                points=driver.points,
                best_case=best_case,
                status=status,
                own_destiny=status != "eliminated" and remaining > 0 and own_destiny(driver),
            )
        )

    if not leader_sure and remaining > 0:
        # A total that no rival can reach, even if the rival wins every round. The leader cannot
        # score that much when a rival wins rounds, so the target only shows when it is possible.
        rivals = max(d.points + remaining * top for d in drivers if d.entry_id != leader.entry_id)
        needed = rivals - leader.points + 1
        if needed <= remaining * top:
            result.leader_target = needed
    return result
