from datetime import date, timedelta
from typing import Annotated, Literal

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile
from pydantic import field_validator

from apps.audit.services import change, record
from apps.common.api import conflict_on_duplicate, require
from apps.competition.permissions import manages_any_championship

from .car_data import tyre_compounds
from .game_images import (
    JPEG,
    MAX_IMAGE_BYTES,
    PNG,
    GameImagesError,
    import_game_images,
    needed_keys,
    open_source,
    save_image,
)
from .game_import import import_from_game
from .models import Car, CarClass, CarClassMembership, CarSkin, Track, TrackLayout, WeatherPreset

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
    has_outline: bool
    has_preview: bool
    length_m: int | None
    country: str
    city: str
    width_m: int | None
    direction: str
    latitude: float | None
    longitude: float | None
    year: int | None
    author: str
    version: str
    url: str
    description: str
    tags: list[str]

    @staticmethod
    def resolve_has_outline(obj) -> bool:
        return bool(obj.outline)

    @staticmethod
    def resolve_has_preview(obj) -> bool:
        return bool(obj.preview)


class GuidanceIn(Schema):
    restart_guidance: str = Field("", max_length=2000)
    first_lap_cutoff: str = Field("", max_length=200)
    pit_boxes: int | None = Field(None, ge=1, le=200)


class TrackIn(Schema):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    country: str = Field("", max_length=100)


class TrackEditIn(Schema):
    name: str = Field(min_length=1, max_length=200)
    # None keeps the country. An empty text removes it.
    country: str | None = Field(None, max_length=100)


class TrackOut(Schema):
    id: int
    key: str
    name: str
    country: str
    layouts: list[LayoutOut]


class CarIn(Schema):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class NameIn(Schema):
    name: str = Field(min_length=1, max_length=200)


def _web_address(value: str | None) -> str | None:
    if value and not value.strip().lower().startswith(("http://", "https://")):
        raise ValueError("url_not_http")
    return value


Tags = list[Annotated[str, Field(max_length=50)]]


class LayoutEditIn(Schema):
    """The fields to change. A field that the request leaves out keeps its value."""

    name: str | None = Field(None, min_length=1, max_length=200)
    length_m: int | None = Field(None, ge=100, le=100_000)
    width_m: int | None = Field(None, ge=1, le=100)
    pit_boxes: int | None = Field(None, ge=1, le=200)
    country: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    direction: Literal["", "clockwise", "anticlockwise"] | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    year: int | None = Field(None, ge=1880, le=2100)
    author: str | None = Field(None, max_length=200)
    version: str | None = Field(None, max_length=50)
    url: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=5000)
    tags: Tags | None = Field(None, max_length=30)

    _url = field_validator("url")(_web_address)


class CarEditIn(Schema):
    """The fields to change. A field that the request leaves out keeps its value."""

    name: str | None = Field(None, min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=100)
    game_class: str | None = Field(None, max_length=60)
    country: str | None = Field(None, max_length=100)
    year: int | None = Field(None, ge=1880, le=2100)
    power_hp: int | None = Field(None, ge=1, le=5000)
    torque_nm: int | None = Field(None, ge=1, le=10_000)
    weight_kg: int | None = Field(None, ge=1, le=20_000)
    top_speed_kmh: int | None = Field(None, ge=1, le=1500)
    acceleration: str | None = Field(None, max_length=60)
    power_to_weight: str | None = Field(None, max_length=60)
    author: str | None = Field(None, max_length=200)
    version: str | None = Field(None, max_length=50)
    url: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=5000)
    tags: Tags | None = Field(None, max_length=30)

    _url = field_validator("url")(_web_address)


def _apply(item, payload: Schema) -> list[dict]:
    """Set the fields that the request sends. A null clears a field. Returns the changes for
    the history, with short texts."""
    changes = []
    for name, value in payload.model_dump(exclude_unset=True).items():
        if name == "name" and not value:
            continue  # A name cannot be empty.
        if isinstance(value, str):
            value = value.strip()
        if value is None and isinstance(getattr(item, name), str):
            value = ""
        if value is None and isinstance(getattr(item, name), list):
            value = []
        old = getattr(item, name)
        if old != value:
            changes.append(
                change(
                    name, str(old)[:80] if old not in (None, "") else None, str(value)[:80] or None
                )
            )
            setattr(item, name, value)
    return changes


class SkinOut(Schema):
    id: int
    key: str
    name: str
    driver_name: str
    team: str
    number: str
    has_preview: bool

    @staticmethod
    def resolve_has_preview(obj) -> bool:
        return bool(obj.preview)


class WearOut(Schema):
    curve: list[list[float]]
    x_95: float | None = None
    x_90: float | None = None
    x_80: float | None = None
    end_x: float
    end_grip: float


class TyreSideOut(Schema):
    width: float | None = None
    radius: float | None = None
    rim_radius: float | None = None
    pressure_ideal: float | None = None
    pressure_static: float | None = None
    wear_curve: str | None = None
    wear: WearOut | None = None


class TyreOut(Schema):
    index: int
    name: str
    short_name: str
    front: TyreSideOut
    rear: TyreSideOut


class CarOut(Schema):
    id: int
    key: str
    name: str
    has_preview: bool
    has_badge: bool
    brand: str
    author: str
    game_class: str
    country: str
    year: int | None
    power_hp: int | None
    torque_nm: int | None
    weight_kg: int | None
    top_speed_kmh: int | None
    acceleration: str
    power_to_weight: str
    specs_text: dict[str, str]
    version: str
    url: str
    description: str
    tags: list[str]
    power_curve: list[list[float]]
    torque_curve: list[list[float]]
    source: str
    source_url: str
    has_data: bool
    data_error: str
    skins: list[SkinOut]
    tyres: list[TyreOut]

    @staticmethod
    def resolve_has_preview(obj) -> bool:
        return bool(obj.preview)

    @staticmethod
    def resolve_has_badge(obj) -> bool:
        return bool(obj.badge)

    @staticmethod
    def resolve_has_data(obj) -> bool:
        return bool(obj.data)

    @staticmethod
    def resolve_skins(obj) -> list:
        return list(obj.skins.all())

    @staticmethod
    def resolve_tyres(obj) -> list[dict]:
        return tyre_compounds(obj.data)


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


@router.get("/cars/{car_id}", response=CarOut)
def get_car(request, car_id: int):
    return get_object_or_404(Car.objects.prefetch_related("skins"), pk=car_id)


@router.get("/layouts/{layout_id}", response=LayoutOut)
def get_layout(request, layout_id: int):
    return get_object_or_404(TrackLayout, pk=layout_id)


class WeatherOut(Schema):
    id: int
    key: str
    name: str
    has_preview: bool
    # What a pilot can use from weather.ini: "cloud_cover" (0 to 1), "fog_distance" (metres of
    # sight), "temp_coeff" (-1 to 1: how much colder or warmer the asphalt is than the weather
    # and the hour say), and "lights_forced" (true: headlights are on). Only what the file has.
    facts: dict[str, float | bool]

    @staticmethod
    def resolve_has_preview(obj) -> bool:
        return bool(obj.preview)

    @staticmethod
    def resolve_facts(obj) -> dict:
        sources = {
            "cloud_cover": ("CLOUDS", "COVER"),
            "fog_distance": ("FOG", "DISTANCE"),
            "temp_coeff": ("LAUNCHER", "TEMPERATURE_COEFF"),
        }
        facts: dict = {}
        for name, (section, key) in sources.items():
            value = obj.data.get(section, {}).get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                facts[name] = value
        forced = obj.data.get("CAR_LIGHTS", {}).get("FORCE_ON")
        if isinstance(forced, int | float) and forced:
            facts["lights_forced"] = True
        return facts


@router.get("/weather", response=list[WeatherOut])
def list_weather(request):
    return WeatherPreset.objects.all()


@router.get("/weather/{weather_id}/preview")
def weather_preview(request, weather_id: int):
    return _image_response(get_object_or_404(WeatherPreset, pk=weather_id).preview)


@router.get("/cars", response=list[CarOut])
def list_cars(request):
    return Car.objects.prefetch_related("skins")


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


@router.patch("/tracks/{track_id}", response=TrackOut)
def edit_track(request, track_id: int, payload: TrackEditIn):
    require(manages_any_championship(request.user))
    track = get_object_or_404(Track, pk=track_id)
    country = track.country if payload.country is None else payload.country.strip()
    changes = [
        change(field, old, new)
        for field, old, new in (
            ("name", track.name, payload.name),
            ("country", track.country, country),
        )
        if old != new
    ]
    track.name = payload.name
    track.country = country
    track.save(update_fields=["name", "country"])
    record(
        request.user,
        "track.renamed",
        "track",
        track.id,
        params={"name": track.name},
        changes=changes,
    )
    return track


@router.patch("/layouts/{layout_id}", response=LayoutOut)
def edit_layout(request, layout_id: int, payload: LayoutEditIn):
    require(manages_any_championship(request.user))
    layout = get_object_or_404(TrackLayout.objects.select_related("track"), pk=layout_id)
    changes = _apply(layout, payload)
    layout.save()
    record(
        request.user,
        "layout.renamed",
        "track",
        layout.track_id,
        params={"name": str(layout)},
        changes=changes,
    )
    return layout


@router.patch("/cars/{car_id}", response=CarOut)
def edit_car(request, car_id: int, payload: CarEditIn):
    require(manages_any_championship(request.user))
    car = get_object_or_404(Car, pk=car_id)
    changes = _apply(car, payload)
    car.save()
    record(
        request.user,
        "car.renamed",
        "car",
        car.id,
        params={"name": car.name},
        changes=changes,
    )
    return car


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


# Pictures from the game files


class NeededTrackOut(Schema):
    track: str
    layout: str


class NeededOut(Schema):
    tracks: list[NeededTrackOut]
    cars: list[str]


class GameImagesReportOut(Schema):
    layouts: list[str]
    cars: list[str]
    missing_layouts: list[str]
    missing_cars: list[str]


MAX_ZIP_BYTES = 200 * 1024 * 1024


class GameImportOut(Schema):
    new_tracks: list[str]
    new_layouts: list[str]
    new_cars: list[str]
    new_weather: list[str]
    layouts: list[str]
    cars: list[str]


@router.get("/game-images/needed", response=NeededOut)
def game_images_needed(request):
    """The track and car folders of the catalog, for tools/pack_game_images.py."""
    require(manages_any_championship(request.user))
    return needed_keys()


@router.post("/game-images", response=GameImagesReportOut)
def upload_game_images(request, file: File[UploadedFile]):
    require(manages_any_championship(request.user))
    if file.size > MAX_ZIP_BYTES:
        raise HttpError(400, "file_too_large")
    try:
        report = import_game_images(open_source(file), request.user)
    except GameImagesError as error:
        raise HttpError(400, error.code) from error
    return report


@router.post("/game-import", response=GameImportOut)
def game_import(request, file: File[UploadedFile]):
    """ "Importar desde el juego": the browser sends the files of the chosen cars and tracks.
    The app adds the ones that are new, with their pictures and data."""
    require(manages_any_championship(request.user))
    if file.size > MAX_ZIP_BYTES:
        raise HttpError(400, "file_too_large")
    try:
        source = open_source(file)
    except GameImagesError as error:
        raise HttpError(400, error.code) from error
    return import_from_game(source, request.user)


def _image_response(field_file):
    if not field_file:
        raise Http404
    handle = field_file.open("rb")
    # A picture from the game files or from an admin can be a PNG, a JPEG, or a WebP.
    head = handle.read(12)
    if head.startswith(PNG):
        content_type = "image/png"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        content_type = "image/webp"
    else:
        content_type = "image/jpeg"
    handle.seek(0)
    response = FileResponse(handle, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cache-Control"] = "private, max-age=86400"
    return response


@router.get("/layouts/{layout_id}/images/{kind}")
def layout_image(request, layout_id: int, kind: str):
    layout = get_object_or_404(TrackLayout, pk=layout_id)
    if kind not in LAYOUT_IMAGES:
        raise Http404
    return _image_response(getattr(layout, kind))


@router.get("/skins/{skin_id}/preview")
def skin_preview(request, skin_id: int):
    return _image_response(get_object_or_404(CarSkin, pk=skin_id).preview)


@router.get("/cars/{car_id}/data")
def car_data(request, car_id: int):
    """All the numbers of the data folder of a car (see car_data.py). It is large, so the car
    list does not carry it."""
    return get_object_or_404(Car, pk=car_id).data


@router.get("/cars/{car_id}/images/{kind}")
def car_image(request, car_id: int, kind: str):
    car = get_object_or_404(Car, pk=car_id)
    if kind not in CAR_IMAGES:
        raise Http404
    return _image_response(getattr(car, kind))


LAYOUT_IMAGES = ("outline", "preview")
CAR_IMAGES = ("preview", "badge")


def _uploaded_image(file: UploadedFile) -> bytes:
    """The bytes of a PNG or a JPEG of at most 5 MB. Any other file is refused."""
    if file.size > MAX_IMAGE_BYTES:
        raise HttpError(400, "image_too_large")
    data = file.read()
    if not (data.startswith(PNG) or data.startswith(JPEG)):
        raise HttpError(400, "image_not_supported")
    return data


@router.post("/layouts/{layout_id}/images/{kind}", response=LayoutOut)
def upload_layout_image(request, layout_id: int, kind: str, file: File[UploadedFile]):
    require(manages_any_championship(request.user))
    layout = get_object_or_404(TrackLayout.objects.select_related("track"), pk=layout_id)
    if kind not in LAYOUT_IMAGES:
        raise Http404
    save_image(getattr(layout, kind), kind, _uploaded_image(file))
    layout.save(update_fields=[kind])
    record(
        request.user, f"layout.{kind}_set", "track", layout.track_id, params={"name": str(layout)}
    )
    return layout


@router.delete("/layouts/{layout_id}/images/{kind}", response=LayoutOut)
def remove_layout_image(request, layout_id: int, kind: str):
    require(manages_any_championship(request.user))
    layout = get_object_or_404(TrackLayout.objects.select_related("track"), pk=layout_id)
    if kind not in LAYOUT_IMAGES:
        raise Http404
    getattr(layout, kind).delete(save=False)
    layout.save(update_fields=[kind])
    record(
        request.user,
        f"layout.{kind}_removed",
        "track",
        layout.track_id,
        params={"name": str(layout)},
    )
    return layout


@router.post("/cars/{car_id}/images/{kind}", response=CarOut)
def upload_car_image(request, car_id: int, kind: str, file: File[UploadedFile]):
    require(manages_any_championship(request.user))
    car = get_object_or_404(Car, pk=car_id)
    if kind not in CAR_IMAGES:
        raise Http404
    save_image(getattr(car, kind), kind, _uploaded_image(file))
    car.save(update_fields=[kind])
    record(request.user, f"car.{kind}_set", "car", car.id, params={"name": car.name})
    return car


@router.delete("/cars/{car_id}/images/{kind}", response=CarOut)
def remove_car_image(request, car_id: int, kind: str):
    require(manages_any_championship(request.user))
    car = get_object_or_404(Car, pk=car_id)
    if kind not in CAR_IMAGES:
        raise Http404
    getattr(car, kind).delete(save=False)
    car.save(update_fields=[kind])
    record(request.user, f"car.{kind}_removed", "car", car.id, params={"name": car.name})
    return car
