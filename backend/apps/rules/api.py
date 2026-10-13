"""The rules editor of a season: versions, a preview against old results, and changes."""

from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.competition.models import Season
from apps.competition.permissions import can_manage, can_view
from apps.results.services import change_rules, preview_rules

from .models import RulesVersion
from .scoring import PointsRules

router = Router(tags=["rules"])


class RulesFields(Schema):
    points_by_position: list[int] = Field(min_length=1, max_length=50)
    pole_bonus: int = Field(0, ge=0, le=50)
    fastest_lap_bonus: int = Field(0, ge=0, le=50)
    ballast_steps: list[int] = Field(max_length=20)
    restrictor_steps: list[int] = Field(max_length=20)
    ballast_cap: int = Field(ge=0, le=200)
    restrictor_cap: int = Field(ge=0, le=100)
    ballast_reduction: int = Field(ge=0, le=200)
    restrictor_reduction: int = Field(ge=0, le=100)


class RulesChangeIn(RulesFields):
    reason: str = Field(min_length=1, max_length=500)
    recalculate: bool = False


class RulesVersionOut(RulesFields):
    number: int
    reason: str
    recalculated: bool
    created_at: datetime
    created_by: str | None


class SeasonRulesOut(Schema):
    can_edit: bool
    versions: list[RulesVersionOut]  # The newest first.


class PreviewRowOut(Schema):
    entry_id: int
    driver_name: str
    current_rank: int
    current_points: int
    new_rank: int
    new_points: int


FIELDS = list(RulesFields.model_fields)


def _check(fields: dict) -> None:
    values = [*fields["points_by_position"], *fields["ballast_steps"], *fields["restrictor_steps"]]
    if any(value < 0 or value > 200 for value in values):
        raise HttpError(422, "rules_value_out_of_range")


def _season(user, season_id: int, manage: bool = False) -> Season:
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(user, season.championship):
        raise Http404
    if manage and not can_manage(user, season.championship):
        raise HttpError(403, "forbidden")
    return season


def _out(user, season: Season) -> SeasonRulesOut:
    RulesVersion.current_for(season)  # A season without rules gets the defaults.
    versions = season.rules_versions.select_related("created_by").order_by("-number")
    return SeasonRulesOut(
        can_edit=can_manage(user, season.championship),
        versions=[
            RulesVersionOut(
                **{name: getattr(v, name) for name in FIELDS},
                number=v.number,
                reason=v.reason,
                recalculated=v.recalculated,
                created_at=v.created_at,
                created_by=v.created_by.username if v.created_by else None,
            )
            for v in versions
        ],
    )


@router.get("/seasons/{season_id}/rules", response=SeasonRulesOut)
def get_rules(request, season_id: int):
    return _out(request.user, _season(request.user, season_id))


@router.post("/seasons/{season_id}/rules/preview", response=list[PreviewRowOut])
def preview(request, season_id: int, payload: RulesFields):
    season = _season(request.user, season_id, manage=True)
    _check(payload.dict())
    names = dict(season.entries.values_list("id", "driver__display_name"))
    rules = PointsRules(
        points_by_position=tuple(payload.points_by_position),
        pole_bonus=payload.pole_bonus,
        fastest_lap_bonus=payload.fastest_lap_bonus,
    )
    return [
        PreviewRowOut(**vars(row), driver_name=names[row.entry_id])
        for row in preview_rules(season, rules)
    ]


@router.post("/seasons/{season_id}/rules", response=SeasonRulesOut)
def change(request, season_id: int, payload: RulesChangeIn):
    season = _season(request.user, season_id, manage=True)
    fields = {name: getattr(payload, name) for name in FIELDS}
    _check(fields)
    change_rules(season, request.user, fields, payload.reason, payload.recalculate)
    return _out(request.user, season)
