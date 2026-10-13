from datetime import date, timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema, Status

from apps.audit.services import change, record
from apps.common.api import conflict_on_duplicate, require
from apps.competition.permissions import manages_any_championship

from .models import Car, CarClass, CarClassMembership, Track, TrackLayout

router = Router(tags=["catalog"])


class LayoutIn(Schema):
    key: str = Field("", max_length=100)
    name: str = Field(min_length=1, max_length=200)
    restart_guidance: str = Field("", max_length=2000)
    first_lap_cutoff: str = Field("", max_length=200)


class LayoutOut(Schema):
    id: int
    key: str
    name: str
    restart_guidance: str
    first_lap_cutoff: str
    pit_boxes: int | None


class GuidanceIn(Schema):
    restart_guidance: str = Field("", max_length=2000)
    first_lap_cutoff: str = Field("", max_length=200)
    pit_boxes: int | None = Field(None, ge=1, le=200)


class TrackIn(Schema):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class TrackOut(Schema):
    id: int
    key: str
    name: str
    layouts: list[LayoutOut]


class CarIn(Schema):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class CarOut(Schema):
    id: int
    key: str
    name: str


@router.get("/tracks", response=list[TrackOut])
def list_tracks(request):
    return Track.objects.prefetch_related("layouts")


@router.post("/tracks", response={201: TrackOut})
def create_track(request, payload: TrackIn):
    require(manages_any_championship(request.user))
    with conflict_on_duplicate("track_exists"):
        track = Track.objects.create(**payload.dict())
        record(request.user, "track.created", "track", track.id, params={"name": track.name})
    return Status(201, track)


@router.post("/tracks/{track_id}/layouts", response={201: LayoutOut})
def create_layout(request, track_id: int, payload: LayoutIn):
    require(manages_any_championship(request.user))
    track = get_object_or_404(Track, pk=track_id)
    with conflict_on_duplicate("layout_exists"):
        layout = TrackLayout.objects.create(track=track, **payload.dict())
        record(
            request.user,
            "layout.created",
            "track",
            track.id,
            params={"track": track.name, "name": layout.name},
        )
    return Status(201, layout)


@router.get("/cars", response=list[CarOut])
def list_cars(request):
    return Car.objects.all()


@router.post("/cars", response={201: CarOut})
def create_car(request, payload: CarIn):
    require(manages_any_championship(request.user))
    with conflict_on_duplicate("car_exists"):
        car = Car.objects.create(**payload.dict())
        record(request.user, "car.created", "car", car.id, params={"name": car.name})
    return Status(201, car)


@router.patch("/layouts/{layout_id}/guidance", response=LayoutOut)
def set_guidance(request, layout_id: int, payload: GuidanceIn):
    require(manages_any_championship(request.user))
    layout = get_object_or_404(TrackLayout, pk=layout_id)
    layout.restart_guidance = payload.restart_guidance
    layout.first_lap_cutoff = payload.first_lap_cutoff
    layout.pit_boxes = payload.pit_boxes
    layout.save(update_fields=["restart_guidance", "first_lap_cutoff", "pit_boxes"])
    record(
        request.user,
        "layout.guidance",
        "track",
        layout.track_id,
        params={"name": str(layout)},
    )
    return layout


class MembershipOut(Schema):
    car_id: int
    car_name: str
    valid_from: date
    valid_to: date | None
    reason: str


class CarClassOut(Schema):
    id: int
    name: str
    car_ids: list[int]  # The cars in the class today.
    history: list[MembershipOut]


class CarClassIn(Schema):
    name: str = Field(min_length=1, max_length=60)


class ClassCarsIn(Schema):
    car_ids: list[int]
    reason: str = Field("", max_length=300)


def _class_out(item: CarClass) -> CarClassOut:
    rows = list(item.memberships.select_related("car"))
    return CarClassOut(
        id=item.id,
        name=item.name,
        car_ids=sorted(r.car_id for r in rows if r.valid_to is None),
        history=[
            MembershipOut(
                car_id=r.car_id,
                car_name=r.car.name,
                valid_from=r.valid_from,
                valid_to=r.valid_to,
                reason=r.reason,
            )
            for r in rows
        ],
    )


@router.get("/classes", response=list[CarClassOut])
def list_classes(request):
    return [_class_out(c) for c in CarClass.objects.prefetch_related("memberships__car")]


@router.post("/classes", response={201: CarClassOut})
def create_class(request, payload: CarClassIn):
    require(manages_any_championship(request.user))
    with conflict_on_duplicate("class_exists"):
        item = CarClass.objects.create(name=payload.name)
        record(request.user, "class.created", "car_class", item.id, params={"name": item.name})
    return Status(201, _class_out(item))


@router.put("/classes/{class_id}/cars", response=CarClassOut)
def set_class_cars(request, class_id: int, payload: ClassCarsIn):
    """Set the cars of the class from today. Old rows stay in the history."""
    require(manages_any_championship(request.user))
    item = get_object_or_404(CarClass, pk=class_id)
    wanted = set(Car.objects.filter(id__in=payload.car_ids).values_list("id", flat=True))
    today = timezone.localdate()
    with transaction.atomic():
        current = {m.car_id: m for m in item.memberships.filter(valid_to__isnull=True)}
        removed = [m for car_id, m in current.items() if car_id not in wanted]
        for membership in removed:
            if membership.valid_from >= today:
                membership.delete()  # Added today by mistake: no history to keep.
            else:
                membership.valid_to = today - timedelta(days=1)
                membership.save(update_fields=["valid_to"])
        added = sorted(wanted - set(current))
        CarClassMembership.objects.bulk_create(
            CarClassMembership(
                car_class=item,
                car_id=car_id,
                valid_from=today,
                reason=payload.reason,
                changed_by=request.user,
            )
            for car_id in added
        )
        names = dict(
            Car.objects.filter(id__in=set(added) | {m.car_id for m in removed}).values_list(
                "id", "name"
            )
        )
        record(
            request.user,
            "class.cars_changed",
            "car_class",
            item.id,
            params={"name": item.name},
            changes=[change("added", None, ", ".join(names[c] for c in added))]
            + [change("removed", ", ".join(names[m.car_id] for m in removed), None)],
            reason=payload.reason,
        )
    return _class_out(item)
