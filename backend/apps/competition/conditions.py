"""The conditions draw: random conditions for a round from the pool of its season."""

import secrets

from django.db import transaction

from apps.audit.services import change, record

from .models import ConditionsDraw, ConditionsPool, Round

RANDOM = secrets.SystemRandom()  # Nobody can predict or repeat a draw.


class DrawError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _range(low: int | None, high: int | None) -> int | None:
    if low is None or high is None:
        return None
    return RANDOM.randint(min(low, high), max(low, high))


def draw_values(pool: ConditionsPool) -> dict:
    values = {
        "weather": RANDOM.choice(pool.weather) if pool.weather else "",
        "time_of_day": RANDOM.choice(pool.time_of_day) if pool.time_of_day else "",
        "grip": RANDOM.choice(pool.grip) if pool.grip else "",
        "air_temp_c": _range(pool.air_temp_min, pool.air_temp_max),
        "track_temp_c": _range(pool.track_temp_min, pool.track_temp_max),
    }
    if not any(v not in ("", None) for v in values.values()):
        raise DrawError("pool_empty")
    return values


def draw(round_: Round, user, reason: str = "") -> ConditionsDraw:
    """Draw the conditions and put them in the round briefing. The notes of the round stay."""
    pool = ConditionsPool.objects.filter(season=round_.season).first()
    if pool is None:
        raise DrawError("pool_empty")
    if hasattr(round_, "result"):
        raise DrawError("round_has_result")
    earlier = round_.conditions_draws.exists()
    if earlier and not reason.strip():
        raise DrawError("reason_required")
    values = draw_values(pool)
    old = dict(round_.announced_conditions or {})
    new = {**old, **values}
    with transaction.atomic():
        item = ConditionsDraw.objects.create(
            round=round_, values=values, reason=reason, drawn_by=user
        )
        round_.announced_conditions = new
        round_.save(update_fields=["announced_conditions"])
        record(
            user,
            "round.conditions_redrawn" if earlier else "round.conditions_drawn",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={"number": round_.number, "track": str(round_.track_layout)},
            changes=[change("announced_conditions", old, new)],
            reason=reason,
        )
    return item
