"""Safety rating, rules version safety-1. Pure functions with no database.

docs/LEAGUE_RULES.md, section "Safety rating", has the rules that the league agreed.
"""

from dataclasses import dataclass, field

RULES_VERSION = "safety-1"
START = 3.00
LOWEST = 0.00
HIGHEST = 5.00
PER_LAP = 0.01
PER_POINT = 0.05
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


@dataclass
class DriverRating:
    rating: float
    status: str  # "unknown", "provisional", or "rated"
    laps: int
    points: int
    per_100_laps: float | None
    history: list[RoundChange]


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
        change = round(item.laps * PER_LAP - round_points * PER_POINT, 2)
        rating = round(min(HIGHEST, max(LOWEST, rating + change)), 2)
        laps += item.laps
        points += round_points
        history.append(
            RoundChange(
                item.round_id,
                item.label,
                "rated",
                item.laps,
                round_points,
                change,
                rating,
                [text for _, _, text in item.incidents],
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
