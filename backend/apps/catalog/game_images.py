"""Read track and car pictures from the Assetto Corsa content folder, or from a ZIP of it.

The ZIP has the same paths as the content folder, so one reader works for both:

    tracks/<track>/ui/<layout>/outline.png, preview.png, ui_track.json
    tracks/<track>/ui/outline.png ...      (a track with one layout)
    cars/<car>/ui/badge.png, ui_car.json
    cars/<car>/preview.jpg                 (in a ZIP: the preview of one skin)
    cars/<car>/skins/<skin>/preview.jpg    (in a folder: the first skin is used)

tools/pack_game_images.py makes the ZIP on a PC with the game.
"""

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from apps.audit.services import record

from .models import Car, TrackLayout

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
MAX_ZIP_ENTRIES = 5000
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
        return []


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
        return sorted(c.name for c in folder.iterdir() if (c / "preview.jpg").is_file())

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
        for info in infos:
            name = info.filename.replace("\\", "/").lstrip("/")
            # Accept a ZIP that has the content folder itself at the top.
            if name.lower().startswith("content/"):
                name = name[len("content/") :]
            if ".." in name.split("/") or info.is_dir():
                continue
            self.index[name.lower()] = info

    def read(self, path: str, limit: int) -> bytes | None:
        info = self.index.get(path.lower())
        if info is None or info.file_size > limit:
            return None
        with self.zip.open(info) as handle:
            data = handle.read(limit + 1)
        return data if len(data) <= limit else None


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


def _length(value) -> int | None:
    match = re.search(r"[\d.,]+", str(value or ""))
    if not match:
        return None
    number = float(match.group(0).replace(",", "."))
    # Some tracks give kilometres ("5.2 km"), most give metres ("12191").
    metres = number * 1000 if "km" in str(value).lower() or number < 100 else number
    return round(metres) if 100 <= metres <= 100_000 else None


def _put(field_file, name: str, data: bytes) -> None:
    if field_file:
        field_file.delete(save=False)
    field_file.save(name, ContentFile(data), save=False)


def _layout_base(layout: TrackLayout) -> str:
    base = f"tracks/{layout.track.key}/ui"
    return f"{base}/{layout.key}" if layout.key else base


@transaction.atomic
def import_game_images(source: _Source, user=None) -> Report:
    report = Report()
    for layout in TrackLayout.objects.select_related("track").order_by("track__key", "key"):
        label = f"{layout.track.key}/{layout.key}" if layout.key else layout.track.key
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
        layout.length_m = _length(info.get("length")) or layout.length_m
        layout.country = str(info.get("country") or layout.country)[:100]
        layout.save()
        report.layouts.append(label)

    for car in Car.objects.order_by("key"):
        base = f"cars/{car.key}"
        badge = _image(source.read(f"{base}/ui/badge.png", MAX_IMAGE_BYTES), PNG)
        preview = _image(source.read(f"{base}/preview.jpg", MAX_IMAGE_BYTES), JPEG)
        for skin in source.skins(car.key):
            if preview:
                break
            preview = _image(source.read(f"{base}/skins/{skin}/preview.jpg", MAX_IMAGE_BYTES), JPEG)
        info = _ui_json(source.read(f"{base}/ui/ui_car.json", MAX_JSON_BYTES))
        if not (badge or preview or info):
            report.missing_cars.append(car.key)
            continue
        if badge:
            _put(car.badge, "badge.png", badge)
        if preview:
            _put(car.preview, "preview.jpg", preview)
        car.brand = str(info.get("brand") or car.brand)[:100]
        car.author = str(info.get("author") or car.author)[:200]
        car.save()
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
