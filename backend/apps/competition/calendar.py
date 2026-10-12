"""Calendar slots of a season."""

from .models import Round, Season


def voted_slots(season: Season) -> int:
    """The rounds that voting can still fill: the planned total minus the existing rounds.

    Example: an eight-round season with two fixed rounds has six voted slots.
    """
    return max(0, season.planned_round_count - season.rounds.count())


def fixed_layout_ids(season: Season) -> set[int]:
    return set(
        season.rounds.filter(origin=Round.Origin.FIXED).values_list("track_layout_id", flat=True)
    )


def next_round_number(season: Season) -> int:
    last = season.rounds.order_by("-number").values_list("number", flat=True).first()
    return (last or 0) + 1
