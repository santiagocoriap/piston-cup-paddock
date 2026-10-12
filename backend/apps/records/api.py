from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.catalog.models import Car, TrackLayout
from apps.competition.permissions import can_manage, can_view
from apps.imports.models import ImportedLap

from .services import invalidate_lap, record_boards

router = Router(tags=["records"])


class RecordLapOut(Schema):
    lap_id: int
    lap_time_ms: int
    driver_name: str
    date: datetime
    round_id: int
    round_number: int
    season_name: str
    championship_name: str
    lap_number: int
    sectors_ms: list[int]
    tyre: str
    ballast_kg: int
    restrictor: int
    conditions: str | None  # The result files have no conditions yet. None means unknown.
    source_file: str
    uploaded_by: str | None
    ineligible_reason: str | None
    can_invalidate: bool


class HistoryOut(Schema):
    kind: str
    lap: RecordLapOut


class BoardOut(Schema):
    layout_id: int
    track_name: str
    layout_name: str
    car_id: int
    car_name: str
    category: str
    record_ms: int | None
    holders: list[RecordLapOut]
    history: list[HistoryOut]


class LayoutOption(Schema):
    id: int
    name: str


class RecordsOut(Schema):
    layouts: list[LayoutOption]
    boards: list[BoardOut]


class InvalidateIn(Schema):
    reason: str = Field(min_length=1, max_length=500)


def _lap_out(user, item, details) -> RecordLapOut:
    lap = details[item.lap_id]
    round_ = lap.result_import.round
    return RecordLapOut(
        lap_id=lap.id,
        lap_time_ms=lap.lap_time_ms,
        driver_name=item.driver_name,
        date=round_.scheduled_at,
        round_id=round_.id,
        round_number=round_.number,
        season_name=round_.season.name,
        championship_name=round_.season.championship.name,
        lap_number=lap.lap_number,
        sectors_ms=lap.sectors_ms,
        tyre=lap.tyre,
        ballast_kg=lap.ballast_kg,
        restrictor=lap.restrictor,
        conditions=None,
        source_file=lap.result_import.filename,
        uploaded_by=lap.result_import.uploaded_by.username
        if lap.result_import.uploaded_by
        else None,
        ineligible_reason=item.ineligible_reason,
        can_invalidate=can_manage(user, round_.season.championship) and not lap.invalid_reason,
    )


@router.get("/records", response=RecordsOut)
def get_records(request, layout_id: int | None = None):
    all_boards, details = record_boards(request.user)
    layout_ids = sorted({b.layout_id for b in all_boards})
    layouts = {
        layout.id: layout
        for layout in TrackLayout.objects.filter(id__in=layout_ids).select_related("track")
    }
    selected = [b for b in all_boards if layout_id is None or b.layout_id == layout_id]
    cars = {car.id: car for car in Car.objects.filter(id__in={b.car_id for b in selected})}
    return RecordsOut(
        layouts=[
            LayoutOption(id=i, name=f"{layouts[i].track.name} · {layouts[i].name}")
            for i in layout_ids
        ],
        boards=[
            BoardOut(
                layout_id=b.layout_id,
                track_name=layouts[b.layout_id].track.name,
                layout_name=layouts[b.layout_id].name,
                car_id=b.car_id,
                car_name=cars[b.car_id].name,
                category=b.category,
                record_ms=b.record_ms,
                holders=[_lap_out(request.user, h, details) for h in b.holders],
                history=[
                    HistoryOut(kind=h.kind, lap=_lap_out(request.user, h.lap, details))
                    for h in b.history
                ],
            )
            for b in selected
        ],
    )


@router.post("/laps/{lap_id}/invalidate", response={204: None})
def invalidate(request, lap_id: int, payload: InvalidateIn):
    lap = get_object_or_404(
        ImportedLap.objects.select_related("result_import__round__season__championship", "entry"),
        pk=lap_id,
    )
    championship = lap.result_import.round.season.championship
    if not can_view(request.user, championship):
        raise Http404
    if not can_manage(request.user, championship):
        raise HttpError(403, "forbidden")
    invalidate_lap(lap, payload.reason, request.user)
    return Status(204, None)
