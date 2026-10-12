from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from apps.competition.models import Round, Season, SeasonEntry
from apps.competition.permissions import can_manage, can_view
from apps.rules.models import RulesVersion

from .models import HandicapAdjustment
from .services import HandicapError, adjust, season_handicaps

router = Router(tags=["handicaps"])


class StepOut(Schema):
    round_id: int
    round_number: int
    position: int | None
    status: str | None
    outcome: str
    season_wins: int
    before_kg: int
    before_pct: int
    change_kg: int
    change_pct: int
    capped: bool
    after_kg: int
    after_pct: int
    used_kg: int | None
    used_pct: int | None
    adjustment_reason: str | None


class EntryHandicapsOut(Schema):
    entry_id: int
    number: int
    driver_name: str
    rounds: list[StepOut]
    next_kg: int
    next_pct: int
    next_adjustment_reason: str | None


class HandicapRulesOut(Schema):
    ballast_steps: list[int]
    restrictor_steps: list[int]
    ballast_cap: int
    restrictor_cap: int
    ballast_reduction: int
    restrictor_reduction: int


class SeasonHandicapsOut(Schema):
    next_round_id: int | None
    next_round_number: int | None
    can_manage: bool
    rules: HandicapRulesOut
    entries: list[EntryHandicapsOut]


class AdjustmentIn(Schema):
    entry_id: int
    round_id: int
    ballast_kg: int = Field(ge=0, le=500)
    restrictor_pct: int = Field(ge=0, le=100)
    mode: HandicapAdjustment.Mode
    reason: str = Field(max_length=500)


def _season(user, season_id: int) -> Season:
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(user, season.championship):
        raise Http404
    return season


def _out(user, season: Season) -> SeasonHandicapsOut:
    values = season_handicaps(season)
    rules = RulesVersion.current_for(season)
    entries = {e.id: e for e in season.entries.select_related("driver")}
    return SeasonHandicapsOut(
        next_round_id=values.next_round_id,
        next_round_number=values.next_round_number,
        can_manage=can_manage(user, season.championship),
        rules=HandicapRulesOut(
            ballast_steps=rules.ballast_steps,
            restrictor_steps=rules.restrictor_steps,
            ballast_cap=rules.ballast_cap,
            restrictor_cap=rules.restrictor_cap,
            ballast_reduction=rules.ballast_reduction,
            restrictor_reduction=rules.restrictor_reduction,
        ),
        entries=[
            EntryHandicapsOut(
                entry_id=item.entry_id,
                number=entries[item.entry_id].number,
                driver_name=entries[item.entry_id].driver.display_name,
                next_kg=item.next_kg,
                next_pct=item.next_pct,
                next_adjustment_reason=item.next_adjustment_reason,
                rounds=[
                    StepOut(
                        round_id=r.round_id,
                        round_number=r.round_number,
                        position=r.position,
                        status=r.status,
                        outcome=r.step.outcome,
                        season_wins=r.step.season_wins,
                        before_kg=r.step.before_kg,
                        before_pct=r.step.before_pct,
                        change_kg=r.step.change_kg,
                        change_pct=r.step.change_pct,
                        capped=r.step.capped,
                        after_kg=r.step.after_kg,
                        after_pct=r.step.after_pct,
                        used_kg=r.used_kg,
                        used_pct=r.used_pct,
                        adjustment_reason=r.adjustment_reason,
                    )
                    for r in item.rounds
                ],
            )
            for item in values.entries
        ],
    )


@router.get("/seasons/{season_id}/handicaps", response=SeasonHandicapsOut)
def get_handicaps(request, season_id: int):
    return _out(request.user, _season(request.user, season_id))


@router.post("/seasons/{season_id}/handicaps/adjustments", response=SeasonHandicapsOut)
def create_adjustment(request, season_id: int, payload: AdjustmentIn):
    season = _season(request.user, season_id)
    if not can_manage(request.user, season.championship):
        raise HttpError(403, "forbidden")
    round_ = get_object_or_404(Round, pk=payload.round_id, season=season)
    entry = get_object_or_404(SeasonEntry, pk=payload.entry_id)
    try:
        adjust(
            round_,
            entry,
            ballast_kg=payload.ballast_kg,
            restrictor_pct=payload.restrictor_pct,
            mode=payload.mode,
            reason=payload.reason,
            user=request.user,
        )
    except HandicapError as error:
        raise HttpError(422, error.code) from error
    return _out(request.user, season)
