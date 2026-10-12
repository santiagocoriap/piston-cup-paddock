from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.errors import HttpError
from pydantic import AwareDatetime

from apps.competition.models import Round, Season
from apps.competition.permissions import can_manage, can_view
from apps.rules.models import RulesVersion
from apps.rules.scoring import Line, ResultError, Status

from .models import RaceResult
from .services import save_result, season_standings

router = Router(tags=["results"])


class RulesOut(Schema):
    version: int
    points_by_position: list[int]
    pole_bonus: int
    fastest_lap_bonus: int


class EntryOption(Schema):
    entry_id: int
    driver_id: int
    number: int
    driver_name: str
    car_name: str


class LineIn(Schema):
    entry_id: int
    status: Status
    position: int | None = Field(None, ge=1, le=200)
    pole: bool = False
    fastest_lap: bool = False


class LineOut(LineIn):
    number: int
    driver_name: str
    points: int


class ResultIn(Schema):
    lines: list[LineIn]
    reason: str = Field("", max_length=500)


class RoundDetail(Schema):
    id: int
    number: int
    season_id: int
    season_name: str
    championship_name: str
    track_name: str
    layout_name: str
    scheduled_at: AwareDatetime
    can_manage: bool
    rules: RulesOut
    entries: list[EntryOption]
    result: list[LineOut] | None


class RoundScoreOut(Schema):
    round_number: int
    status: str | None
    position: int | None
    points: int


class StandingOut(Schema):
    rank: int
    entry_id: int
    number: int
    driver_name: str
    car_name: str
    team: str
    points: int
    wins: int
    rounds: list[RoundScoreOut]


STATUS_ORDER = {Status.FINISHED: 0, Status.DNF: 0, Status.DSQ: 1, Status.DNS: 2}


def _visible_round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _round_detail(user, round_: Round) -> RoundDetail:
    season = round_.season
    result = RaceResult.objects.filter(round=round_).select_related("rules_version").first()
    rules = result.rules_version if result else RulesVersion.current_for(season)
    entries = season.entries.select_related("driver", "car")
    lines = None
    if result:
        rows = sorted(
            result.lines.select_related("entry__driver"),
            key=lambda r: (STATUS_ORDER[Status(r.status)], r.position or 0, r.entry.number),
        )
        lines = [
            LineOut(
                entry_id=r.entry_id,
                status=r.status,
                position=r.position,
                pole=r.pole,
                fastest_lap=r.fastest_lap,
                number=r.entry.number,
                driver_name=r.entry.driver.display_name,
                points=r.points,
            )
            for r in rows
        ]
    return RoundDetail(
        id=round_.id,
        number=round_.number,
        season_id=season.id,
        season_name=season.name,
        championship_name=season.championship.name,
        track_name=round_.track_layout.track.name,
        layout_name=round_.track_layout.name,
        scheduled_at=round_.scheduled_at,
        can_manage=can_manage(user, season.championship),
        rules=RulesOut(
            version=rules.number,
            points_by_position=rules.points_by_position,
            pole_bonus=rules.pole_bonus,
            fastest_lap_bonus=rules.fastest_lap_bonus,
        ),
        entries=[
            EntryOption(
                entry_id=e.id,
                driver_id=e.driver_id,
                number=e.number,
                driver_name=e.driver.display_name,
                car_name=e.car.name,
            )
            for e in entries
        ],
        result=lines,
    )


@router.get("/rounds/{round_id}", response=RoundDetail)
def get_round(request, round_id: int):
    return _round_detail(request.user, _visible_round(request.user, round_id))


@router.put("/rounds/{round_id}/result", response=RoundDetail)
def put_result(request, round_id: int, payload: ResultIn):
    """Replace the race classification of the round and calculate the points."""
    round_ = _visible_round(request.user, round_id)
    if not can_manage(request.user, round_.season.championship):
        raise HttpError(403, "forbidden")
    lines = [
        Line(line.entry_id, line.status, line.position, line.pole, line.fastest_lap)
        for line in payload.lines
    ]
    try:
        save_result(round_, lines, request.user, payload.reason)
    except ResultError as error:
        raise HttpError(422, error.code) from error
    return _round_detail(request.user, round_)


@router.get("/seasons/{season_id}/standings", response=list[StandingOut])
def get_standings(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    entries = {e.id: e for e in season.entries.select_related("driver", "car")}
    return [
        StandingOut(
            rank=row.rank,
            entry_id=row.entry_id,
            number=entries[row.entry_id].number,
            driver_name=entries[row.entry_id].driver.display_name,
            car_name=entries[row.entry_id].car.name,
            team=entries[row.entry_id].team,
            points=row.points,
            wins=row.wins,
            rounds=[RoundScoreOut(**vars(score)) for score in row.rounds],
        )
        for row in season_standings(season)
    ]
