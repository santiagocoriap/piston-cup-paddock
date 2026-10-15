"""Add tracks and cars from the game files, with their pictures and data.

The admin picks the assettocorsa folder in the browser. The browser lists the cars and the
tracks, and sends a ZIP with the files of the chosen ones (the same paths as the content
folder, as for game_images.py). The app creates each car, track, and layout that is not in the
catalog yet, then fills the pictures and the data from the same ZIP.
"""

import re
from dataclasses import dataclass, field

from django.db import transaction

from apps.audit.services import record

from .game_images import MAX_JSON_BYTES, ZipSource, _ui_json, import_game_images
from .models import Car, Track, TrackLayout

# A folder name of AC: other text cannot be a key (the server files use the keys).
KEY = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")
TRACK_JSON = re.compile(r"^tracks/([^/]+)/ui/(?:([^/]+)/)?ui_track\.json$", re.IGNORECASE)
CAR_JSON = re.compile(r"^cars/([^/]+)/ui/ui_car\.json$", re.IGNORECASE)
DEFAULT_LAYOUT = "GP"


@dataclass
class ImportReport:
    new_tracks: list[str] = field(default_factory=list)
    new_layouts: list[str] = field(default_factory=list)
    new_cars: list[str] = field(default_factory=list)
    layouts: list[str] = field(default_factory=list)  # With pictures or data.
    cars: list[str] = field(default_factory=list)


def _common_name(names: list[str]) -> str:
    """The shared start of the layout names, for the track name: "Highlands Long" and
    "Highlands Short" give "Highlands"."""
    if len(names) == 1:
        return names[0]
    words = [name.split() for name in names]
    shared = []
    for group in zip(*words, strict=False):
        if len({word.lower() for word in group}) != 1:
            break
        shared.append(group[0])
    return " ".join(shared).strip(" -·")


def _layout_name(full: str, track_name: str, key: str) -> str:
    rest = (
        full[len(track_name) :].strip(" -·") if full.lower().startswith(track_name.lower()) else ""
    )
    return rest or full or key or DEFAULT_LAYOUT


def read_selection(source: ZipSource) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """The tracks ({track key: {layout key: name}}) and the cars ({key: name}) in the ZIP."""
    tracks: dict[str, dict[str, str]] = {}
    cars: dict[str, str] = {}
    for info in source.index.values():
        name = info.filename.replace("\\", "/").lstrip("/")
        if name.lower().startswith("content/"):
            name = name[len("content/") :]
        if match := TRACK_JSON.match(name):
            track, layout = match[1], match[2] or ""
            if KEY.match(track) and (not layout or KEY.match(layout)):
                info_json = _ui_json(source.read(name, MAX_JSON_BYTES))
                tracks.setdefault(track, {})[layout] = str(info_json.get("name") or "").strip()
        elif match := CAR_JSON.match(name):
            if KEY.match(match[1]):
                info_json = _ui_json(source.read(name, MAX_JSON_BYTES))
                cars[match[1]] = str(info_json.get("name") or "").strip() or match[1]
    return tracks, cars


@transaction.atomic
def import_from_game(source: ZipSource, user=None) -> ImportReport:
    report = ImportReport()
    tracks, cars = read_selection(source)
    layout_labels: set[str] = set()
    for key, layouts in sorted(tracks.items()):
        names = [name for name in layouts.values() if name]
        track_name = _common_name(names) if names else key
        track = Track.objects.filter(key__iexact=key).first()
        if track is None:
            track = Track.objects.create(key=key, name=track_name or key)
            report.new_tracks.append(key)
        for layout_key, full in sorted(layouts.items()):
            label = f"{track.key}/{layout_key}" if layout_key else track.key
            layout_labels.add(label)
            if not track.layouts.filter(key__iexact=layout_key).exists():
                name = (
                    _layout_name(full, track.name, layout_key)
                    if len(layouts) > 1
                    else (layout_key or DEFAULT_LAYOUT)
                )
                TrackLayout.objects.create(track=track, key=layout_key, name=name)
                report.new_layouts.append(label)
    for key, name in sorted(cars.items()):
        if not Car.objects.filter(key__iexact=key).exists():
            Car.objects.create(key=key, name=name)
            report.new_cars.append(key)
    images = import_game_images(source, only_layouts=layout_labels, only_cars=set(cars))
    report.layouts, report.cars = images.layouts, images.cars
    if user is not None:
        record(
            user,
            "catalog.game_import",
            "catalog",
            0,
            params={
                "tracks": len(report.new_tracks),
                "layouts": len(report.new_layouts),
                "cars": len(report.new_cars),
            },
        )
    return report
