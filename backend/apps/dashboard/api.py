from datetime import datetime

from ninja import Router, Schema

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
