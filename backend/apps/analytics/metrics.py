"""The statistics of the data analysis pages. Pure functions with no database.

Every formula of the analysis pages is here, so the pages only draw the numbers. A value that
the data cannot give is None: the app never invents a value.
"""

import math
import random
import statistics
from dataclasses import dataclass

# A statistic of spread needs at least this many laps.
MIN_LAPS_FOR_SPREAD = 3
TRIM_SHARE = 0.1  # The trimmed mean leaves out this share of laps at each end.
# At the line, a car this close behind another car is "attacking" it, or "defending" from it.
BATTLE_GAP_MS = 1000
MIN_TREND_POINTS = 4
ELO_START = 1500.0
ELO_K = 24.0


def trimmed_mean(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = int(len(ordered) * TRIM_SHARE)
    kept = ordered[cut : len(ordered) - cut] or ordered
    return sum(kept) / len(kept)


def mad(values: list[int]) -> float | None:
    """The median absolute deviation: the middle distance of a lap from the median lap."""
    if len(values) < MIN_LAPS_FOR_SPREAD:
        return None
    middle = statistics.median(values)
    return statistics.median(abs(value - middle) for value in values)


@dataclass
class Spread:
    """The numbers of a box plot. low and high are the last values inside 1.5 box heights."""

    count: int
    mean: float | None = None
    median: float | None = None
    trimmed: float | None = None
    stdev: float | None = None
    mad: float | None = None
    q1: float | None = None
    q3: float | None = None
    low: float | None = None
    high: float | None = None
    outliers: tuple[float, ...] = ()


def spread(values: list[int]) -> Spread:
    if not values:
        return Spread(0)
    result = Spread(
        count=len(values),
        mean=sum(values) / len(values),
        median=statistics.median(values),
        trimmed=trimmed_mean(values),
    )
    if len(values) < MIN_LAPS_FOR_SPREAD:
        return result
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    limit = 1.5 * (q3 - q1)
    inside = [v for v in values if q1 - limit <= v <= q3 + limit]
    result.stdev = statistics.stdev(values)
    result.mad = mad(values)
    result.q1, result.q3 = q1, q3
    result.low, result.high = min(inside), max(inside)
    result.outliers = tuple(sorted(v for v in values if v not in inside))
    return result


@dataclass
class LapOrder:
    """One driver at the end of one lap. The gaps are at the line, in ms."""

    position: int
    gap_to_leader_ms: int
    ahead_ms: int | None
    behind_ms: int | None


def lap_order(times_by_driver: dict[object, list[int]]) -> dict[object, list[LapOrder]]:
    """The order at the end of each lap, from the sum of the lap times. A driver counts on a lap
    only after the driver completes it. So a lapped driver drops behind on the laps that the
    leader alone completed, and the order is the order at the line, not on the track."""
    totals: dict[object, list[int]] = {}
    for key, times in times_by_driver.items():
        running = 0
        totals[key] = []
        for ms in times:
            running += ms
            totals[key].append(running)
    longest = max((len(values) for values in totals.values()), default=0)
    orders: dict[object, list[LapOrder]] = {key: [] for key in totals}
    for lap in range(longest):
        row = sorted(
            (values[lap], str(key), key) for key, values in totals.items() if len(values) > lap
        )
        leader = row[0][0]
        for index, (total, _, key) in enumerate(row):
            orders[key].append(
                LapOrder(
                    position=index + 1,
                    gap_to_leader_ms=total - leader,
                    ahead_ms=total - row[index - 1][0] if index else None,
                    behind_ms=row[index + 1][0] - total if index + 1 < len(row) else None,
                )
            )
    return orders


def battle_share(order: list[LapOrder]) -> dict[str, int]:
    """The laps of a driver at the line: attacking a car, defending from a car, or alone."""
    counts = {"attacking": 0, "defending": 0, "clean_air": 0}
    for lap in order:
        if lap.ahead_ms is not None and lap.ahead_ms <= BATTLE_GAP_MS:
            counts["attacking"] += 1
        elif lap.behind_ms is not None and lap.behind_ms <= BATTLE_GAP_MS:
            counts["defending"] += 1
        else:
            counts["clean_air"] += 1
    return counts


def elo(races: list[list[tuple[object, int]]]) -> dict[object, list[float]]:
    """A pairwise Elo rating. Each race is a list of (driver, finish position). Each pair of
    drivers in a race is one match with K/(n - 1) as the weight. A driver gets a value after each
    race of the driver. All drivers start at 1500."""
    ratings: dict[object, float] = {}
    history: dict[object, list[float]] = {}
    for race in races:
        if len(race) < 2:
            continue
        weight = ELO_K / (len(race) - 1)
        current = {key: ratings.get(key, ELO_START) for key, _ in race}
        change = dict.fromkeys(current, 0.0)
        for key, position in race:
            for other, other_position in race:
                if other == key:
                    continue
                expected = 1 / (1 + math.pow(10, (current[other] - current[key]) / 400))
                actual = 1.0 if position < other_position else 0.0
                actual = 0.5 if position == other_position else actual
                change[key] += weight * (actual - expected)
        for key in current:
            ratings[key] = current[key] + change[key]
            history.setdefault(key, []).append(round(ratings[key], 1))
    return history


@dataclass
class Odds:
    win_pct: float
    expected_rank: float
    rank_odds: list[float]  # The percent chance of each final rank: the first value is P1.


def predict(
    points: dict[object, int],
    history: dict[object, list[int]],
    remaining: int,
    *,
    runs: int = 2000,
    seed: int = 0,
) -> dict[object, Odds]:
    """A Monte Carlo estimate of the final standings. In each run, each remaining round gives each
    driver the points of one past round of that same driver, by chance. This model is simple: it
    does not stop 2 drivers from taking the same place, and a tie in points goes to chance."""
    keys = list(points)
    rng = random.Random(seed)
    counts = {key: [0] * len(keys) for key in keys}
    for _ in range(runs):
        totals = []
        for key in keys:
            past = history.get(key) or [0]
            total = points[key] + sum(rng.choice(past) for _ in range(remaining))
            totals.append((-total, rng.random(), key))
        for rank, (_, _, key) in enumerate(sorted(totals)):
            counts[key][rank] += 1
    return {
        key: Odds(
            win_pct=round(counts[key][0] * 100 / runs, 1),
            expected_rank=round(sum((i + 1) * n for i, n in enumerate(counts[key])) / runs, 2),
            rank_odds=[round(n * 100 / runs, 1) for n in counts[key]],
        )
        for key in keys
    }


def trend(values: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """A straight line through (x, y) points: (slope, value at x = 0, standard error of a point).
    None with fewer than MIN_TREND_POINTS points."""
    if len(values) < MIN_TREND_POINTS:
        return None
    xs = [x for x, _ in values]
    ys = [y for _, y in values]
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    bottom = sum((x - mean_x) ** 2 for x in xs)
    if bottom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in values) / bottom
    start = mean_y - slope * mean_x
    errors = [(y - (start + slope * x)) ** 2 for x, y in values]
    return slope, start, math.sqrt(sum(errors) / (len(values) - 2))


def scale(values: dict[object, float | None], *, lower_is_better: bool) -> dict[object, int | None]:
    """A score from 0 to 100 inside the field: 100 is the best value, and 0 is the worst."""
    known = [v for v in values.values() if v is not None]
    if len(known) < 2:
        return {key: None for key in values}
    low, high = min(known), max(known)
    if low == high:
        return {key: (None if v is None else 50) for key, v in values.items()}

    def score(value: float) -> int:
        share = (value - low) / (high - low)
        return round((1 - share if lower_is_better else share) * 100)

    return {key: (None if v is None else score(v)) for key, v in values.items()}
