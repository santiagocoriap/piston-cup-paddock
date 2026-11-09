from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.competition.models import Round, Season
from apps.competition.permissions import can_view
from apps.dashboard.api import _driver as visible_driver

from .handicap_effect import handicap_effect
from .services import add_telemetry, round_analysis, season_analysis

router = Router(tags=["analytics"])


class LapSpreadOut(Schema):
    count: int
    mean: float | None
    median: float | None
    trimmed: float | None
    stdev: float | None
    mad: float | None
    q1: float | None
    q3: float | None
    low: float | None
    high: float | None
    outliers: list[float]


class LapPointOut(Schema):
    number: int
    ms: int
    sectors_ms: list[int]
    valid: bool
    clean: bool
    pit: str | None
    contact: bool
    tyre: str
    position: int | None
    gap_to_leader_ms: int | None
    ahead_ms: int | None
    fuel_used: float | None
    fuel_left: float | None
    pit_ms: int | None
    wear: float | None


class DriverStintOut(Schema):
    start_lap: int
    end_lap: int
    tyre: str
    laps: int
    median_ms: float | None
    trend_ms: float | None
    pit_loss_ms: int | None


class RoundDriverOut(Schema):
    entry_id: int
    driver_id: int
    name: str
    number: int
    grid: int | None
    finish: int | None
    status: str | None
    points: int | None
    best_ms: int | None
    best_lap: int | None
    theoretical_ms: int | None
    best_sectors_ms: list[int | None]
    spread: LapSpreadOut
    battle: dict[str, int] | None
    laps: list[LapPointOut]
    stints: list[DriverStintOut]
    overtakes: int | None
    overtaken: int | None
    attacks: int | None
    attacks_won: int | None
    defenses: int | None
    defenses_won: int | None
    battle_seconds: int | None


class OvertakeOut(Schema):
    at_s: int
    lap: int
    attacker_id: int
    defender_id: int
    x: float | None
    z: float | None


class RoundAnalysisOut(Schema):
    session: str
    sessions: list[str]
    has_sectors: bool
    has_pit_data: bool
    clean_rules: list[str]
    drivers: list[RoundDriverOut]
    has_positions: bool
    overtakes: list[OvertakeOut]


class RoundCellOut(Schema):
    round_id: int
    number: int
    track: str
    grid: int | None
    finish: int | None
    status: str | None
    points: int
    total_points: int
    rank: int | None
    gap_to_leader: int | None
    pole: bool
    fastest_lap: bool
    best_ms: int | None
    median_ms: float | None
    stdev_ms: float | None
    pace_pct: float | None
    qualifying_pct: float | None
    elo: float | None
    overtakes: int | None
    attacks: int | None
    attacks_won: int | None
    defenses: int | None
    defenses_won: int | None
    incidents: int | None
    sectors_ms: list[int | None]


class ForecastOut(Schema):
    number: int
    value: float
    low: float
    high: float


class RivalryOut(Schema):
    a: int
    b: int
    battles: int
    seconds: int
    passes: int


class SeasonDriverOut(Schema):
    entry_id: int
    driver_id: int
    name: str
    number: int
    rank: int
    points: int
    wins: int
    podiums: int
    poles: int
    fastest_laps: int
    finishes: int
    dnfs: int
    cells: list[RoundCellOut]
    scores: dict[str, int | None]
    average_pace_pct: float | None
    average_stdev_ms: float | None
    max_points: int | None
    can_win: bool | None
    win_pct: float | None
    expected_rank: float | None
    rank_odds: list[float] | None
    pace_trend: float | None
    pace_forecast: list[ForecastOut]


class SeasonRoundOut(Schema):
    id: int
    number: int
    track: str
    has_result: bool
    circuit_type: str | None
    corners: int | None
    field_spread_pct: float | None


class SeasonAnalysisOut(Schema):
    season_id: int
    season_name: str
    championship_name: str
    planned_rounds: int
    remaining_rounds: int
    points_by_position: list[int]
    rounds: list[SeasonRoundOut]
    drivers: list[SeasonDriverOut]
    rivalries: list[RivalryOut]


@router.get("/rounds/{round_id}/analysis", response=RoundAnalysisOut)
def get_round_analysis(
    request, round_id: int, session: Literal["race", "qualifying", "practice"] = "race"
):
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    analysis = round_analysis(round_, session)
    add_telemetry(analysis, round_, request.user)
    return analysis


@router.get("/seasons/{season_id}/analysis", response=SeasonAnalysisOut)
def get_season_analysis(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    return season_analysis(season)


@router.get("/drivers/{driver_id}/analysis", response=list[SeasonAnalysisOut])
def get_driver_analysis(request, driver_id: int):
    """The analysis of each season of the driver that the viewer can see. The driver page shows
    the row of the driver and the field around it. A rival comes from the same seasons."""
    driver = visible_driver(request.user, driver_id)
    seasons = (
        Season.objects.filter(entries__driver=driver)
        .select_related("championship")
        .order_by("-id")
        .distinct()
    )
    return [season_analysis(s) for s in seasons if can_view(request.user, s.championship)]


class HandicapRoundOut(Schema):
    number: int
    ballast_kg: int
    restrictor_pct: int
    laps: int | None
    lap_ms: float | None
    model_ms: float | None
    pace_pct: float | None


class HandicapDriverOut(Schema):
    entry_id: int
    driver_id: int
    name: str
    car: str
    rounds: list[HandicapRoundOut]
    model_total_ms: float | None
    model_pct: float | None
    measured_pct: float | None


class HandicapCarOut(Schema):
    car_id: int
    name: str
    weight_kg: int | None
    power_hp: int | None
    lap_ms: float | None
    per_10kg_ms: float | None
    per_1pct_ms: float | None


class HandicapEffectOut(Schema):
    mass_exponent: float
    power_exponent: float
    driver_kg: int
    cars: list[HandicapCarOut]
    drivers: list[HandicapDriverOut]
    model_pct: float | None
    measured_pct: float | None


@router.get("/seasons/{season_id}/handicap-effect", response=HandicapEffectOut)
def get_handicap_effect(request, season_id: int):
    """How much time the ballast and the restrictor cost: a model estimate and the lap times."""
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    return handicap_effect(season)
