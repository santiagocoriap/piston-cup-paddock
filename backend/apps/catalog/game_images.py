"""Read track and car pictures from the Assetto Corsa content folder, or from a ZIP of it.

The ZIP has the same paths as the content folder, so one reader works for both:

    tracks/<track>/ui/<layout>/outline.png, preview.png, ui_track.json
    tracks/<track>/ui/outline.png ...      (a track with one layout)
    cars/<car>/ui/badge.png, ui_car.json
    cars/<car>/preview.jpg                 (in a ZIP: the preview of one skin)
    cars/<car>/skins/<skin>/preview.jpg    (in a folder: the first skin is used)

tools/pack_game_images.py makes the ZIP on a PC with the game.
"""

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from apps.audit.services import record

from .acd import AcdError, read_acd
from .car_data import read_car_data
from .game_facts import car_facts, fill_empty, layout_facts
from .models import Car, CarClass, CarClassMembership, CarSkin, TrackLayout

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
MAX_ZIP_ENTRIES = 30_000
MAX_ACD_BYTES = 20 * 1024 * 1024
MAX_DATA_FILE_BYTES = 2 * 1024 * 1024
MAX_PICTURE_PIXELS = 40_000_000
THUMBNAIL_SIDE = 640
KUNOS = re.compile(r"^(?:kunos|ks_|assetto corsa)", re.IGNORECASE)
SKIN_FILE = re.compile(r"^cars/([^/]+)/skins/([^/]+)/[^/]+$", re.IGNORECASE)
DATA_FILE = re.compile(r"^cars/([^/]+)/data/([^/]+)$", re.IGNORECASE)
PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"


class GameImagesError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Report:
    layouts: list[str] = field(default_factory=list)
    cars: list[str] = field(default_factory=list)
    missing_layouts: list[str] = field(default_factory=list)
    missing_cars: list[str] = field(default_factory=list)


class _Source:
    """Files by their path in the content folder, matched without case."""

    def read(self, path: str, limit: int) -> bytes | None:
        raise NotImplementedError

    def skins(self, car_key: str) -> list[str]:
        """The skin folders of a car, with the case of the folder."""
        return []

    def data_files(self, car_key: str) -> dict[str, bytes]:
        """The files of an unpacked data folder, by lower case name."""
        return {}


class FolderSource(_Source):
    def __init__(self, root: Path):
        if (root / "content").is_dir():
            root = root / "content"
        if not (root / "tracks").is_dir() and not (root / "cars").is_dir():
            raise GameImagesError("not_a_content_folder")
        self.root = root

    def _find(self, path: str) -> Path | None:
        current = self.root
        for part in path.split("/"):
            if not current.is_dir():
                return None
            exact = current / part
            if exact.exists():
                current = exact
                continue
            match = next((c for c in current.iterdir() if c.name.lower() == part.lower()), None)
            if match is None:
                return None
            current = match
        return current if current.is_file() else None

    def read(self, path: str, limit: int) -> bytes | None:
        found = self._find(path)
        if found is None or found.stat().st_size > limit:
            return None
        return found.read_bytes()

    def skins(self, car_key: str) -> list[str]:
        folder = self._find_dir(f"cars/{car_key}/skins")
        if folder is None:
            return []
        return sorted(
            c.name
            for c in folder.iterdir()
            if c.is_dir() and ((c / "preview.jpg").is_file() or (c / "ui_skin.json").is_file())
        )

    def data_files(self, car_key: str) -> dict[str, bytes]:
        folder = self._find_dir(f"cars/{car_key}/data")
        if folder is None:
            return {}
        return {
            c.name.lower(): c.read_bytes()
            for c in folder.iterdir()
            if c.is_file() and c.stat().st_size <= MAX_DATA_FILE_BYTES
        }

    def _find_dir(self, path: str) -> Path | None:
        current = self.root
        for part in path.split("/"):
            match = next((c for c in current.iterdir() if c.name.lower() == part.lower()), None)
            if match is None or not match.is_dir():
                return None
            current = match
        return current


class ZipSource(_Source):
    def __init__(self, file):
        try:
            self.zip = zipfile.ZipFile(file)
        except zipfile.BadZipFile as error:
            raise GameImagesError("bad_zip") from error
        infos = self.zip.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise GameImagesError("too_many_files")
        self.index = {}
        self.names = {}  # The path with its own case, by lower case path.
        for info in infos:
            name = info.filename.replace("\\", "/").lstrip("/")
            # Accept a ZIP that has the content folder itself at the top.
            if name.lower().startswith("content/"):
                name = name[len("content/") :]
            if ".." in name.split("/") or info.is_dir():
                continue
            self.index[name.lower()] = info
            self.names[name.lower()] = name

    def read(self, path: str, limit: int) -> bytes | None:
        info = self.index.get(path.lower())
        if info is None or info.file_size > limit:
            return None
        with self.zip.open(info) as handle:
            data = handle.read(limit + 1)
        return data if len(data) <= limit else None

    def skins(self, car_key: str) -> list[str]:
        found = set()
        for name in self.names.values():
            match = SKIN_FILE.match(name)
            if match and match[1].lower() == car_key.lower():
                found.add(match[2])
        return sorted(found)

    def data_files(self, car_key: str) -> dict[str, bytes]:
        files = {}
        for lower, name in self.names.items():
            match = DATA_FILE.match(name)
            if match and match[1].lower() == car_key.lower():
                if (content := self.read(lower, MAX_DATA_FILE_BYTES)) is not None:
                    files[match[2].lower()] = content
        return files


def open_source(path_or_file) -> _Source:
    if isinstance(path_or_file, (str, Path)):
        path = Path(path_or_file)
        if path.is_dir():
            return FolderSource(path)
        if path.is_file():
            return ZipSource(path.open("rb"))
        raise GameImagesError("not_found")
    return ZipSource(path_or_file)


def _image(data: bytes | None, kind: bytes) -> bytes | None:
    return data if data and data.startswith(kind) else None


def _ui_json(data: bytes | None) -> dict:
    """The game writes loose JSON: a BOM, raw line breaks, sometimes trailing commas."""
    if not data:
        return {}
    text = data.decode("utf-8-sig", errors="replace")
    try:
        value = json.loads(text, strict=False)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        result = {}
        for key in ("name", "length", "country", "brand", "author"):
            match = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
            if match:
                result[key] = match.group(1)
        return result


def save_image(field_file, kind: str, data: bytes) -> None:
    """Store a PNG or a JPEG in a picture field. The file name gets the right extension."""
    _put(field_file, f"{kind}.png" if data.startswith(PNG) else f"{kind}.jpg", data)


def _put(field_file, name: str, data: bytes) -> None:
    if field_file:
        field_file.delete(save=False)
    field_file.save(name, ContentFile(data), save=False)


def _layout_base(layout: TrackLayout) -> str:
    base = f"tracks/{layout.track.key}/ui"
    return f"{base}/{layout.key}" if layout.key else base


def make_thumbnail(data: bytes | None, side: int = THUMBNAIL_SIDE) -> bytes | None:
    """A small WebP of a picture, or None when the bytes are not a picture. The game pictures
    are large (a skin preview is 1920x1080), and a car can have 30 skins."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.width * picture.height > MAX_PICTURE_PIXELS:
                return None
            picture.thumbnail((side, side))
            out = io.BytesIO()
            picture.convert("RGB").save(out, "WEBP", quality=78, method=4)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _put_thumbnail(field_file, name: str, data: bytes | None) -> bool:
    thumbnail = make_thumbnail(data)
    if thumbnail is None:
        return False
    _put(field_file, f"{name}.webp", thumbnail)
    return True


def _source_of(car: Car, info: dict, base: str, source: "_Source") -> tuple[str, str]:
    """(source, address): a car with ui/dlc_ui_car.json is a DLC. Another car of Kunos is in the
    base game, and every other car is a mod."""
    dlc = _ui_json(source.read(f"{base}/ui/dlc_ui_car.json", MAX_JSON_BYTES))
    if dlc or source.read(f"{base}/ui/dlc_preview.png", MAX_IMAGE_BYTES):
        return Car.Source.DLC, car_facts(dlc)["url"]
    author = str(info.get("author") or "")
    if KUNOS.match(author) or KUNOS.match(car.key):
        return Car.Source.BASE, ""
    return Car.Source.MOD, ""


def _read_data(source: "_Source", car: Car) -> tuple[dict, str]:
    """(data, error): from data.acd, or from an unpacked data folder."""
    files = source.data_files(car.key)
    if not files:
        archive = source.read(f"cars/{car.key}/data.acd", MAX_ACD_BYTES)
        if archive is None:
            return {}, ""
        try:
            files = read_acd(archive, car.key)
        except AcdError as error:
            return {}, str(error)
    return read_car_data(files), ""


def _import_skins(source: "_Source", car: Car) -> int:
    """One CarSkin for each skin folder. A picture or a name that the files do not give stays."""
    count = 0
    for folder in source.skins(car.key):
        base = f"cars/{car.key}/skins/{folder}"
        info = _ui_json(source.read(f"{base}/ui_skin.json", MAX_JSON_BYTES))
        skin, _ = CarSkin.objects.get_or_create(car=car, key=folder[:100])
        skin.name = str(info.get("skinname") or "").strip()[:200] or skin.name
        skin.driver_name = str(info.get("drivername") or "").strip()[:200] or skin.driver_name
        skin.team = str(info.get("team") or "").strip()[:200] or skin.team
        skin.number = str(info.get("number") or "").strip()[:20] or skin.number
        priority = info.get("priority")
        if isinstance(priority, int) and not isinstance(priority, bool):
            skin.priority = max(-32000, min(32000, priority))
        preview = source.read(f"{base}/preview.jpg", MAX_IMAGE_BYTES) or source.read(
            f"{base}/preview.png", MAX_IMAGE_BYTES
        )
        _put_thumbnail(skin.preview, "preview", preview)
        skin.save()
        count += 1
    return count


def _import_class(car: Car) -> None:
    """The game class of the car (ui_car.json "class") becomes a car class, once. An admin
    curates the classes after that, so a car that was ever in a class is not changed."""
    name = car.game_class.strip()[:60]
    if not name or car.class_memberships.exists():
        return
    car_class, _ = CarClass.objects.get_or_create(name__iexact=name, defaults={"name": name})
    CarClassMembership.objects.create(
        car_class=car_class, car=car, valid_from=date.today(), reason="Game files"
    )


@transaction.atomic
def import_game_images(
    source: _Source,
    user=None,
    only_layouts: set[str] | None = None,
    only_cars: set[str] | None = None,
) -> Report:
    """only_layouts and only_cars: work on these only ("track/layout" labels and car keys).
    None: every layout and car of the catalog."""
    report = Report()
    for layout in TrackLayout.objects.select_related("track").order_by("track__key", "key"):
        label = f"{layout.track.key}/{layout.key}" if layout.key else layout.track.key
        if only_layouts is not None and label.lower() not in {x.lower() for x in only_layouts}:
            continue
        base = _layout_base(layout)
        outline = _image(source.read(f"{base}/outline.png", MAX_IMAGE_BYTES), PNG)
        preview = _image(source.read(f"{base}/preview.png", MAX_IMAGE_BYTES), PNG)
        info = _ui_json(source.read(f"{base}/ui_track.json", MAX_JSON_BYTES))
        if not (outline or preview or info):
            report.missing_layouts.append(label)
            continue
        if outline:
            _put(layout.outline, "outline.png", outline)
        if preview:
            _put(layout.preview, "preview.png", preview)
        # The facts fill only empty fields, so an admin edit stays.
        fill_empty(layout, layout_facts(info))
        layout.save()
        # The track gets the country of the game files, unless an admin already set one.
        if layout.country and not layout.track.country:
            layout.track.country = layout.country
            layout.track.save(update_fields=["country"])
        report.layouts.append(label)

    for car in Car.objects.order_by("key"):
        if only_cars is not None and car.key.lower() not in {x.lower() for x in only_cars}:
            continue
        base = f"cars/{car.key}"
        badge = _image(source.read(f"{base}/ui/badge.png", MAX_IMAGE_BYTES), PNG)
        preview = source.read(f"{base}/preview.jpg", MAX_IMAGE_BYTES)
        if preview is None or not _image(preview, JPEG):
            preview = None
            for skin in source.skins(car.key):
                found = source.read(f"{base}/skins/{skin}/preview.jpg", MAX_IMAGE_BYTES)
                if _image(found, JPEG):
                    preview = found
                    break
        info = _ui_json(source.read(f"{base}/ui/ui_car.json", MAX_JSON_BYTES))
        data, data_error = _read_data(source, car)
        skins = source.skins(car.key)
        if not (badge or preview or info or data or data_error or skins):
            report.missing_cars.append(car.key)
            continue
        if badge:
            _put(car.badge, "badge.png", badge)
        if preview and not _put_thumbnail(car.preview, "preview", preview):
            # Not readable as a picture: keep it as it is.
            _put(car.preview, "preview.jpg", preview)
        fill_empty(car, car_facts(info))
        if info or source.read(f"{base}/ui/dlc_ui_car.json", MAX_JSON_BYTES):
            car.source, car.source_url = _source_of(car, info, base, source)
        if data or data_error:
            car.data, car.data_error = data, data_error
        car.save()
        _import_skins(source, car)
        _import_class(car)
        report.cars.append(car.key)

    if user is not None:
        record(
            user,
            "catalog.game_images",
            "catalog",
            0,
            params={"layouts": len(report.layouts), "cars": len(report.cars)},
        )
    return report


def needed_keys() -> dict:
    """The folders that the pack script must copy: every layout and car of the catalog."""
    return {
        "tracks": [
            {"track": layout.track.key, "layout": layout.key}
            for layout in TrackLayout.objects.select_related("track").order_by("track__key", "key")
        ],
        "cars": list(Car.objects.order_by("key").values_list("key", flat=True)),
    }
