from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status

from apps.audit.services import record
from apps.common.api import conflict_on_duplicate, require
from apps.competition.permissions import manages_any_championship

from .models import Car, Track, TrackLayout

router = Router(tags=["catalog"])


class LayoutIn(Schema):
    key: str = Field("", max_length=100)
    name: str = Field(min_length=1, max_length=200)


class LayoutOut(Schema):
    id: int
    key: str
    name: str


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
