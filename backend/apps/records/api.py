from datetime import date, datetime
from typing import Literal

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.audit.services import record
from apps.catalog.models import Car, CarClass, TrackLayout
from apps.competition.models import Championship, Season
from apps.competition.permissions import can, can_view, visible_championships
from apps.identity.models import DriverProfile
from apps.imports.models import ImportedLap

from .models import ManualRecord
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
    conditions: dict  # The announced conditions of the round. Empty when unknown.
    source_file: str
    uploaded_by: str | None
    ineligible_reason: str | None
    can_invalidate: bool
    manual: bool = False
    verified: bool | None = None  # Only for a manual record.
    manual_id: int | None = None
    can_verify: bool = False


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
    ranking: list[RecordLapOut]


class LayoutOption(Schema):
    id: int
    name: str


class RecordsOut(Schema):
    layouts: list[LayoutOption]
    cars: list[LayoutOption]
    classes: list[LayoutOption]
    seasons: list[LayoutOption]
    boards: list[BoardOut]


class ManualRecordIn(Schema):
    championship_id: int
    layout_id: int
    car_id: int
    category: Literal["qualifying", "race"]
    lap_time_ms: int = Field(ge=1000, le=3_600_000)
    driver_id: int | None = None
    driver_name: str = Field(min_length=1, max_length=100)
    date: date
    source: str = Field(min_length=1, max_length=300)


class InvalidateIn(Schema):
    reason: str = Field(min_length=1, max_length=500)


def _manual_out(user, item, record: ManualRecord) -> RecordLapOut:
    may = can(user, record.championship, "records")
    return RecordLapOut(
        lap_id=item.lap_id,
        lap_time_ms=record.lap_time_ms,
        driver_name=record.driver_name,
        date=item.date,
        round_id=0,
        round_number=0,
        season_name="",
        championship_name=record.championship.name,
        lap_number=0,
        sectors_ms=[],
        tyre="",
        ballast_kg=0,
        restrictor=0,
        conditions={},
        source_file=record.source,
        uploaded_by=None,
        ineligible_reason=None,
        can_invalidate=False,
        manual=True,
        verified=record.verified_at is not None,
        manual_id=record.id,
        can_verify=may and record.verified_at is None,
    )


def _lap_out(user, item, details) -> RecordLapOut:
    if item.lap_id < 0:
        return _manual_out(user, item, details[item.lap_id])
    lap = details[item.lap_id]
    round_ = lap.result_import.round
    return RecordLapOut(
        lap_id=lap.id,
        lap_time_ms=lap.lap_time_ms,
        driver_name=item.driver_name,
        date=round_.scheduled_at or lap.result_import.uploaded_at,
        round_id=round_.id,
        round_number=round_.number,
        season_name=round_.season.name,
        championship_name=round_.season.championship.name,
        lap_number=lap.lap_number,
        sectors_ms=lap.sectors_ms,
        tyre=lap.tyre,
        ballast_kg=lap.ballast_kg,
        restrictor=lap.restrictor,
        conditions=round_.announced_conditions or {},
        source_file=lap.result_import.filename,
        uploaded_by=lap.result_import.uploaded_by.username
        if lap.result_import.uploaded_by
        else None,
        ineligible_reason=item.ineligible_reason,
        can_invalidate=can(user, round_.season.championship, "records") and not lap.invalid_reason,
    )


@router.get("/records", response=RecordsOut)
def get_records(
    request,
    layout_id: int | None = None,
    car_id: int | None = None,
    category: Literal["qualifying", "race"] | None = None,
    season_id: int | None = None,
    overall: bool = False,
    car_class_id: int | None = None,
):
    every, _ = record_boards(request.user)
    all_boards, details = record_boards(
        request.user,
        car_id=car_id,
        category=category,
        season_id=season_id,
        overall=overall,
        car_class_id=car_class_id,
    )
    car_class = CarClass.objects.filter(pk=car_class_id).first() if car_class_id else None
    layout_ids = sorted({b.layout_id for b in every})
    layouts = {
        layout.id: layout
        for layout in TrackLayout.objects.filter(id__in=layout_ids).select_related("track")
    }
    selected = [b for b in all_boards if layout_id is None or b.layout_id == layout_id]
    cars = {car.id: car for car in Car.objects.filter(id__in={b.car_id for b in every})}
    seasons = (
        Season.objects.filter(
            championship__in=visible_championships(request.user), rounds__result__isnull=False
        )
        .select_related("championship")
        .distinct()
    )
    return RecordsOut(
        layouts=[
            LayoutOption(id=i, name=f"{layouts[i].track.name} · {layouts[i].name}")
            for i in layout_ids
        ],
        cars=[LayoutOption(id=c.id, name=c.name) for c in sorted(cars.values(), key=str)],
        classes=[LayoutOption(id=c.id, name=c.name) for c in CarClass.objects.all()],
        seasons=[LayoutOption(id=s.id, name=f"{s.championship.name} {s.name}") for s in seasons],
        boards=[
            BoardOut(
                layout_id=b.layout_id,
                track_name=layouts[b.layout_id].track.name,
                layout_name=layouts[b.layout_id].name,
                car_id=b.car_id,
                car_name=cars[b.car_id].name if b.car_id else (car_class.name if car_class else ""),
                category=b.category,
                record_ms=b.record_ms,
                holders=[_lap_out(request.user, h, details) for h in b.holders],
                history=[
                    HistoryOut(kind=h.kind, lap=_lap_out(request.user, h.lap, details))
                    for h in b.history
                ],
                ranking=[_lap_out(request.user, r, details) for r in b.ranking],
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
    if not can(request.user, championship, "records"):
        raise HttpError(403, "forbidden")
    invalidate_lap(lap, payload.reason, request.user)
    return Status(204, None)


@router.post("/records/manual", response={201: None})
def add_manual(request, payload: ManualRecordIn):
    championship = get_object_or_404(Championship, pk=payload.championship_id)
    if not can_view(request.user, championship):
        raise Http404
    if not can(request.user, championship, "records"):
        raise HttpError(403, "forbidden")
    layout = get_object_or_404(TrackLayout, pk=payload.layout_id)
    car = get_object_or_404(Car, pk=payload.car_id)
    driver = (
        DriverProfile.objects.filter(pk=payload.driver_id).first() if payload.driver_id else None
    )
    with transaction.atomic():
        item = ManualRecord.objects.create(
            championship=championship,
            layout=layout,
            car=car,
            category=payload.category,
            lap_time_ms=payload.lap_time_ms,
            driver=driver,
            driver_name=driver.display_name if driver else payload.driver_name,
            date=payload.date,
            source=payload.source,
            created_by=request.user,
        )
        record(
            request.user,
            "record.manual_added",
            "championship",
            championship.id,
            championship=championship,
            params={"driver": item.driver_name, "track": str(layout), "time_ms": item.lap_time_ms},
            reason=payload.source,
        )
    return Status(201, None)


def _manual(user, record_id: int) -> ManualRecord:
    item = get_object_or_404(ManualRecord.objects.select_related("championship"), pk=record_id)
    if not can_view(user, item.championship):
        raise Http404
    if not can(user, item.championship, "records"):
        raise HttpError(403, "forbidden")
    return item


@router.post("/records/manual/{record_id}/verify", response={204: None})
def verify_manual(request, record_id: int):
    item = _manual(request.user, record_id)
    item.verified_by = request.user
    item.verified_at = timezone.now()
    item.save(update_fields=["verified_by", "verified_at"])
    record(
        request.user,
        "record.manual_verified",
        "championship",
        item.championship_id,
        championship=item.championship,
        params={"driver": item.driver_name, "track": str(item.layout), "time_ms": item.lap_time_ms},
    )
    return Status(204, None)


@router.delete("/records/manual/{record_id}", response={204: None})
def delete_manual(request, record_id: int):
    item = _manual(request.user, record_id)
    record(
        request.user,
        "record.manual_removed",
        "championship",
        item.championship_id,
        championship=item.championship,
        params={"driver": item.driver_name, "track": str(item.layout), "time_ms": item.lap_time_ms},
    )
    item.delete()
    return Status(204, None)
