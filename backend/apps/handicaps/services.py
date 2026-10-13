"""Ballast and restrictor of a season, from the current result of each round."""

from dataclasses import dataclass, field

from django.db import transaction

from apps.audit.services import change, record
from apps.competition.models import Round, Season, SeasonEntry
from apps.results.models import RaceResult
from apps.rules.handicaps import Outcome, Override, Step, progression
from apps.rules.models import RulesVersion
from apps.rules.scoring import CLASSIFIED, Status

from .models import HandicapAdjustment, UsedHandicap


class HandicapError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class RoundValues:
    round_id: int
    round_number: int
    step: Step
    position: int | None
    status: str | None
    used_kg: int | None
    used_pct: int | None
    adjustment_reason: str | None


@dataclass
class EntryHandicaps:
    entry_id: int
    rounds: list[RoundValues] = field(default_factory=list)
    next_kg: int = 0
    next_pct: int = 0
    next_adjustment_reason: str | None = None


@dataclass
class SeasonHandicaps:
    next_round_id: int | None
    next_round_number: int | None
    entries: list[EntryHandicaps]


def _outcome(line) -> Outcome:
    if line is None or line.status == Status.DNS:
        return Outcome.ABSENT
    if line.status in CLASSIFIED and line.position == 1:
        return Outcome.WIN
    return Outcome.LOSS


def season_handicaps(season: Season, *, before_round: Round | None = None) -> SeasonHandicaps:
    """The values of each driver for each round with a result, and for the next round.

    With `before_round`, only the rounds before it count. The result is then the values that
    the drivers carry into that round.
    """
    rules = RulesVersion.current_for(season).as_handicap_rules()
    rounds = list(season.rounds.order_by("number"))
    results = {
        r.round_id: r
        for r in RaceResult.objects.filter(round__season=season, current_version__isnull=False)
    }
    if before_round is not None:
        rounds = [r for r in rounds if r.number < before_round.number]
        next_round = before_round
    else:
        next_round = next((r for r in rounds if r.id not in results), None)
    raced = [r for r in rounds if r.id in results]

    lines: dict[int, dict[int, object]] = {}
    for round_ in raced:
        version = results[round_.id].current_version
        lines[round_.id] = {line.entry_id: line for line in version.lines.all()}
    adjustments = {
        (a.entry_id, a.round_id): a for a in HandicapAdjustment.objects.filter(round__season=season)
    }
    used = {(u.entry_id, u.round_id): u for u in UsedHandicap.objects.filter(round__season=season)}

    entries = []
    for entry in season.entries.order_by("number"):
        outcomes, overrides = [], {}
        for index, round_ in enumerate(raced):
            outcomes.append(_outcome(lines[round_.id].get(entry.id)))
            adjustment = adjustments.get((entry.id, round_.id))
            if adjustment:
                overrides[index] = _override(adjustment)
        result = progression(outcomes, rules, overrides)
        values = EntryHandicaps(entry_id=entry.id, next_kg=result.next_kg, next_pct=result.next_pct)
        for index, round_ in enumerate(raced):
            line = lines[round_.id].get(entry.id)
            frozen = used.get((entry.id, round_.id))
            adjustment = adjustments.get((entry.id, round_.id))
            values.rounds.append(
                RoundValues(
                    round_id=round_.id,
                    round_number=round_.number,
                    step=result.steps[index],
                    position=getattr(line, "position", None),
                    status=getattr(line, "status", None),
                    used_kg=frozen.ballast_kg if frozen else None,
                    used_pct=frozen.restrictor_pct if frozen else None,
                    adjustment_reason=adjustment.reason if adjustment else None,
                )
            )
        if next_round is not None:
            adjustment = adjustments.get((entry.id, next_round.id))
            if adjustment:
                values.next_kg, values.next_pct = adjustment.ballast_kg, adjustment.restrictor_pct
                values.next_adjustment_reason = adjustment.reason
        entries.append(values)
    return SeasonHandicaps(
        next_round_id=next_round.id if next_round else None,
        next_round_number=next_round.number if next_round else None,
        entries=entries,
    )


def _override(adjustment: HandicapAdjustment) -> Override:
    return Override(
        adjustment.ballast_kg,
        adjustment.restrictor_pct,
        persistent=adjustment.mode == HandicapAdjustment.Mode.PERSISTENT,
    )


def save_used_values(round_: Round) -> None:
    """Keep the values that the drivers carried into this race. Call it before the first
    result of the round. Later corrections never change these values."""
    if UsedHandicap.objects.filter(round=round_).exists():
        return
    values = season_handicaps(round_.season, before_round=round_)
    UsedHandicap.objects.bulk_create(
        UsedHandicap(
            entry_id=entry.entry_id,
            round=round_,
            ballast_kg=entry.next_kg,
            restrictor_pct=entry.next_pct,
        )
        for entry in values.entries
    )


def adjust(
    round_: Round,
    entry: SeasonEntry,
    *,
    ballast_kg: int,
    restrictor_pct: int,
    mode: str,
    reason: str,
    user,
) -> HandicapAdjustment:
    if not reason.strip():
        raise HandicapError("reason_required")
    if entry.season_id != round_.season_id:
        raise HandicapError("entry_not_in_season")
    rules = RulesVersion.current_for(round_.season)
    if ballast_kg > rules.ballast_cap or restrictor_pct > rules.restrictor_cap:
        raise HandicapError("above_cap")
    with transaction.atomic():
        old = HandicapAdjustment.objects.filter(entry=entry, round=round_).first()
        adjustment, _ = HandicapAdjustment.objects.update_or_create(
            entry=entry,
            round=round_,
            defaults={
                "ballast_kg": ballast_kg,
                "restrictor_pct": restrictor_pct,
                "mode": mode,
                "reason": reason,
                "created_by": user,
            },
        )
        record(
            user,
            "handicap.adjusted",
            "season",
            round_.season_id,
            championship=round_.season.championship,
            params={
                "driver": entry.driver.display_name,
                "number": round_.number,
                "season": round_.season.name,
            },
            changes=[
                change("ballast_kg", old.ballast_kg if old else None, ballast_kg),
                change("restrictor_pct", old.restrictor_pct if old else None, restrictor_pct),
                change("mode", old.mode if old else None, mode),
            ],
            reason=reason,
        )
    return adjustment


def assigned_values(round_: Round) -> dict[int, tuple[int, int]]:
    """The ballast (kg) and restrictor (%) of each entry for this round. The saved values when
    the round has a result, else the values that the drivers carry into the round."""
    used = {
        u.entry_id: (u.ballast_kg, u.restrictor_pct)
        for u in UsedHandicap.objects.filter(round=round_)
    }
    if used:
        return used
    values = season_handicaps(round_.season, before_round=round_)
    return {e.entry_id: (e.next_kg, e.next_pct) for e in values.entries}


@dataclass
class HandicapCheck:
    entry_id: int
    driver_name: str
    assigned_kg: int
    assigned_pct: int
    observed_kg: int
    observed_pct: int


def handicap_checks(round_: Round) -> list[HandicapCheck]:
    """The drivers whose race file shows other ballast or restrictor than assigned."""
    from apps.competition.models import Session
    from apps.imports.models import ImportedLap, ResultImport

    race_import = (
        ResultImport.objects.filter(
            round=round_, session__kind=Session.Kind.RACE, status=ResultImport.State.APPLIED
        )
        .order_by("-applied_at")
        .first()
    )
    if race_import is None:
        return []
    assigned = assigned_values(round_)
    observed: dict[int, tuple[int, int, str]] = {}
    laps = ImportedLap.objects.filter(result_import=race_import, entry__isnull=False)
    for lap in laps.select_related("entry__driver").order_by("lap_number"):
        observed.setdefault(
            lap.entry_id, (lap.ballast_kg, lap.restrictor, lap.entry.driver.display_name)
        )
    checks = []
    for entry_id, (kg, pct, name) in observed.items():
        expected = assigned.get(entry_id)
        if expected and (kg, pct) != expected:
            checks.append(HandicapCheck(entry_id, name, expected[0], expected[1], kg, pct))
    return sorted(checks, key=lambda c: c.driver_name)
