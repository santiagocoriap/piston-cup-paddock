"""Safety rating, rules version safety-2. Pure functions with no database.

docs/LEAGUE_RULES.md, section "Safety rating", has the rules that the league agreed.

As in iRacing, the rating compares incidents to the distance driven. Different from iRacing,
the target is the field of the same race: a driver with fewer incident points per lap than the
field goes up, and a driver with more goes down. So a hard track or a chaotic night does not
punish all drivers. A change gets smaller near the ends of the scale, so 0.00 is hard to reach.
"""

from dataclasses import dataclass, field

RULES_VERSION = "safety-2"
START = 2.50
LOWEST = 0.00
HIGHEST = 4.99
MAX_STEP = 0.40  # The change of a full race that is as clean as possible, at the start value.
FULL_LAPS = 20  # A round with fewer laps changes the rating less.
ENV_POINTS = 1
CAR_POINTS = 2
FAST_KMH = 100  # A faster impact counts double.
PROVISIONAL_LAPS = 50


def incident_points(kind: str, max_speed: float) -> int:
    points = CAR_POINTS if kind == "car" else ENV_POINTS
    return points * 2 if max_speed > FAST_KMH else points


@dataclass
class RoundInput:
    round_id: int
    label: str
    laps: int  # Laps driven in the accepted race start.
    covered: bool  # False when the round has no collector events.
    incidents: list[tuple[str, float, str]] = field(default_factory=list)  # kind, speed, text
    # All the drivers of the round together: incident points and laps.
    field_points: int = 0
    field_laps: int = 0


@dataclass
class RoundChange:
    round_id: int
    label: str
    status: str  # "rated" or "unknown"
    laps: int
    points: int
    change: float
    rating_after: float
    explanation: list[str]  # The incidents that gave points.
    per_100_laps: float | None = None  # The driver in this round.
    field_per_100_laps: float | None = None  # All the drivers of this round.


@dataclass
class DriverRating:
    rating: float
    status: str  # "unknown", "provisional", or "rated"
    laps: int
    points: int
    per_100_laps: float | None
    history: list[RoundChange]


def round_score(points: int, laps: int, field_points: int, field_laps: int) -> float:
    """From -1 to +1: +1 for no incidents, 0 for the field rate, -1 for twice the field rate
    or more. A field with no incidents gives +1 to each driver with no incidents."""
    mine = points / max(laps, 1)
    rate_of_field = field_points / field_laps if field_laps else 0.0
    if rate_of_field == 0:
        return 1.0 if points == 0 else -1.0
    return max(-1.0, min(1.0, (rate_of_field - mine) / rate_of_field))


def step(rating: float, score: float, laps: int) -> float:
    """The change of one round. A gain gets smaller near the top, a loss near the bottom."""
    size = MAX_STEP * score * min(1.0, laps / FULL_LAPS)
    room = (HIGHEST - rating) if size > 0 else (rating - LOWEST)
    return size * room / (HIGHEST - START if size > 0 else START - LOWEST)


def rate(rounds: list[RoundInput]) -> DriverRating:
    """The rating after each round, in round order."""
    rating = START
    laps = points = 0
    history = []
    for item in rounds:
        if not item.covered:
            history.append(
                RoundChange(item.round_id, item.label, "unknown", item.laps, 0, 0.0, rating, [])
            )
            continue
        round_points = sum(incident_points(kind, speed) for kind, speed, _ in item.incidents)
        score = round_score(round_points, item.laps, item.field_points, item.field_laps)
        before = rating
        rating = round(min(HIGHEST, max(LOWEST, rating + step(rating, score, item.laps))), 2)
        laps += item.laps
        points += round_points
        history.append(
            RoundChange(
                item.round_id,
                item.label,
                "rated",
                item.laps,
                round_points,
                round(rating - before, 2),
                rating,
                [text for _, _, text in item.incidents],
                round(round_points / item.laps * 100, 1) if item.laps else None,
                round(item.field_points / item.field_laps * 100, 1) if item.field_laps else None,
            )
        )
    if laps == 0:
        status = "unknown"
    elif laps < PROVISIONAL_LAPS:
        status = "provisional"
    else:
        status = "rated"
    return DriverRating(
        rating=rating,
        status=status,
        laps=laps,
        points=points,
        per_100_laps=round(points / laps * 100, 1) if laps else None,
        history=history,
    )
