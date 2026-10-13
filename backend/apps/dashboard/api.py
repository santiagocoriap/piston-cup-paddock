from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from apps.collectors.safety_api import driver_ratings
from apps.competition.models import Championship
from apps.competition.permissions import can_manage, is_league_admin
from apps.identity.models import DriverProfile

from .profile import adjust_career, can_see_driver, career, records, restarts_caused, seasons
from .services import driver_dashboard

router = Router(tags=["dashboard"])


class RecentOut(Schema):
    round_id: int
    round_number: int
    track_name: str
    status: str
    position: int | None
    points: int


class NextRoundOut(Schema):
    round_id: int
    round_number: int
    track_name: str
    layout_name: str
    scheduled_at: datetime | None
    event_timezone: str
    ballast_kg: int
    restrictor_pct: int


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


class DashboardOut(Schema):
    has_driver_profile: bool
    seasons: list[SeasonCardOut]


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
        seasons=[ProfileSeasonOut(**vars(row)) for row in seasons(user, driver)],
        safety=[
            ProfileSafetyOut(
                championship_name=name,
                rating=rating.rating,
                status=rating.status,
                laps=rating.laps,
                points=rating.points,
            )
            for name, rating in driver_ratings(user, driver)
        ],
        records=[ProfileRecordOut(**vars(row)) for row in records(user, driver)],
        restarts_caused=[ProfileRestartOut(**vars(row)) for row in restarts_caused(user, driver)],
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
