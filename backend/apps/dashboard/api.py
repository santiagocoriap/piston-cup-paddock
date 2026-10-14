from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from apps.collectors.safety_api import driver_ratings
from apps.competition.models import Championship, Round
from apps.competition.permissions import can_manage, can_view, is_league_admin
from apps.identity.models import DriverProfile

from .pending import pending
from .profile import (
    achievements,
    adjust_career,
    can_see_driver,
    career,
    records,
    restarts_caused,
    seasons,
    stats,
)
from .round_tabs import tab_counts
from .search import search
from .services import driver_dashboard

router = Router(tags=["dashboard"])


class RecentOut(Schema):
    round_id: int
    round_number: int
    track_name: str
    status: str
    position: int | None
    points: int


class ConditionsOut(Schema):
    time_of_day: str | None = None
    weather: str | None = None
    air_temp_c: int | None = None
    track_temp_c: int | None = None
    grip: str | None = None


class NextRoundOut(Schema):
    round_id: int
    round_number: int
    track_name: str
    layout_name: str
    scheduled_at: datetime | None
    event_timezone: str
    ballast_kg: int
    restrictor_pct: int
    my_attendance: str | None
    attending: int
    previous_ballast_kg: int | None
    previous_restrictor_pct: int | None
    conditions: ConditionsOut | None
    track_outline_url: str | None
    track_preview_url: str | None
    car_image_url: str | None
    ballast_cap: int
    restrictor_cap: int


class NearbyOut(Schema):
    rank: int
    name: str
    points: int
    me: bool


class NewReportOut(Schema):
    round_id: int
    round_number: int
    track_name: str


class SeasonCardOut(Schema):
    season_id: int
    season_name: str
    championship_name: str
    entry_number: int
    car_name: str
    rank: int
    entries: int
    points: int
    wins: int
    leader_points: int
    recent: list[RecentOut]
    next_round: NextRoundOut | None
    new_reports: list[NewReportOut]
    history: list[RecentOut]
    nearby: list[NearbyOut]


class DashboardOut(Schema):
    has_driver_profile: bool
    seasons: list[SeasonCardOut]


class PendingItemOut(Schema):
    path: str
    name: str
    championship: str | None
    number: int | None


class PendingOut(Schema):
    kind: str
    count: int
    items: list[PendingItemOut]


class SearchHitOut(Schema):
    kind: str
    label: str
    detail: str
    path: str
    number: int | None


@router.get("/search", response=list[SearchHitOut])
def search_all(request, q: str = ""):
    """The search box in the header. It needs two letters or more."""
    return search(request.user, q)


@router.get("/pending", response=list[PendingOut])
def pending_list(request):
    """What waits for this admin. A user who manages nothing gets an empty list."""
    return pending(request.user)


@router.get("/dashboard", response=DashboardOut)
def dashboard(request):
    cards = driver_dashboard(request.user)
    has_profile = hasattr(request.user, "driver_profile")
    return DashboardOut(
        has_driver_profile=has_profile,
        seasons=[SeasonCardOut(**vars(card)) for card in cards],
    )


# Driver profile


class AdjustmentOut(Schema):
    kind: str
    points: int
    reason: str
    created_by: str | None
    created_at: datetime


class CareerOut(Schema):
    raw_points: int
    points: int
    level: int
    next_level_points: int
    adjustments: list[AdjustmentOut]


class ProfileSeasonOut(Schema):
    season_id: int
    season_name: str
    championship_name: str
    rank: int
    entries: int
    points: int
    wins: int
    podiums: int
    starts: int
    number: int
    car_name: str
    team: str
    history: list[RecentOut]


class StatsOut(Schema):
    starts: int
    wins: int
    podiums: int
    top5: int
    poles: int
    fastest_laps: int
    best_finish: int | None
    average_finish: float | None
    points: int
    laps: int
    records: int
    win_rate: float | None
    dnfs: int
    dsqs: int
    penalties: int
    incident_points: int
    restarts_caused: int


class AchievementOut(Schema):
    key: str
    count: int
    goal: int
    achieved: bool


class ProfileSafetyOut(Schema):
    championship_name: str
    rating: float
    status: str
    laps: int
    points: int


class ProfileRecordOut(Schema):
    track: str
    car: str
    category: str
    lap_time_ms: int
    round_id: int


class ProfileRestartOut(Schema):
    round_id: int
    label: str
    attempt: int
    reason: str
    shared: bool


class ProfileOut(Schema):
    id: int
    display_name: str
    can_adjust: bool
    career: CareerOut
    seasons: list[ProfileSeasonOut]
    safety: list[ProfileSafetyOut]
    records: list[ProfileRecordOut]
    restarts_caused: list[ProfileRestartOut]
    achievements: list[AchievementOut]
    stats: StatsOut


class AdjustIn(Schema):
    kind: Literal["adjust", "reset"]
    points: int = Field(0, ge=-10000, le=10000)
    reason: str = Field(min_length=1, max_length=500)


def _can_adjust(user, driver: DriverProfile) -> bool:
    if is_league_admin(user):
        return True
    championships = Championship.objects.filter(seasons__entries__driver=driver).distinct()
    return any(can_manage(user, c) for c in championships)


def _profile(user, driver: DriverProfile) -> ProfileOut:
    data = career(driver)
    season_rows = seasons(user, driver)
    record_rows = records(user, driver)
    restart_rows = restarts_caused(user, driver)
    ratings = driver_ratings(user, driver)
    return ProfileOut(
        id=driver.id,
        display_name=driver.display_name,
        can_adjust=_can_adjust(user, driver),
        career=CareerOut(
            raw_points=data.raw_points,
            points=data.points,
            level=data.level,
            next_level_points=data.next_level_points,
            adjustments=[
                AdjustmentOut(
                    kind=a.kind,
                    points=a.points,
                    reason=a.reason,
                    created_by=a.created_by.username if a.created_by else None,
                    created_at=a.created_at,
                )
                for a in data.adjustments
            ],
        ),
        seasons=[
            ProfileSeasonOut(
                **{**vars(row), "history": [RecentOut(**vars(r)) for r in row.history]}
            )
            for row in season_rows
        ],
        safety=[
            ProfileSafetyOut(
                championship_name=name,
                rating=rating.rating,
                status=rating.status,
                laps=rating.laps,
                points=rating.points,
            )
            for name, rating in ratings
        ],
        records=[ProfileRecordOut(**vars(row)) for row in record_rows],
        restarts_caused=[ProfileRestartOut(**vars(row)) for row in restart_rows],
        stats=StatsOut(
            **vars(
                stats(
                    driver,
                    season_rows,
                    len(record_rows),
                    len(restart_rows),
                    sum(rating.points for _, rating in ratings),
                )
            )
        ),
        achievements=[
            AchievementOut(key=a.key, count=a.count, goal=a.goal, achieved=a.achieved)
            for a in achievements(driver, season_rows, len(record_rows))
        ],
    )


def _driver(user, driver_id: int) -> DriverProfile:
    driver = get_object_or_404(DriverProfile, pk=driver_id)
    if not can_see_driver(user, driver):
        raise Http404
    return driver


@router.get("/drivers/{driver_id}/profile", response=ProfileOut)
def driver_profile(request, driver_id: int):
    return _profile(request.user, _driver(request.user, driver_id))


@router.post("/drivers/{driver_id}/career", response=ProfileOut)
def adjust(request, driver_id: int, payload: AdjustIn):
    driver = _driver(request.user, driver_id)
    if not _can_adjust(request.user, driver):
        raise HttpError(403, "forbidden")
    adjust_career(driver, request.user, payload.kind, payload.points, payload.reason)
    return _profile(request.user, driver)


class TabCountsOut(Schema):
    laps: int
    incidents: int
    replay: int
    restarts: int
    telemetry: int
    reports: int


@router.get("/rounds/{round_id}/tab-counts", response=TabCountsOut)
def round_tab_counts(request, round_id: int):
    """How much data each tab of the round page has."""
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(request.user, round_.season.championship):
        raise Http404
    return TabCountsOut(**vars(tab_counts(request.user, round_)))
