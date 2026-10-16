"""Importar desde el juego: new cars, tracks, and layouts from the files of the game."""

import io
import json
import zipfile

import pytest

from apps.catalog.models import Car, Track

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JPEG = b"\xff\xd8\xff" + b"0" * 20


def game_zip(files: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    buffer.seek(0)
    buffer.name = "game.zip"
    return buffer


def ui(**values) -> bytes:
    return json.dumps(values).encode()


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


def send(api, user, files):
    return api(user).client.post("/api/catalog/game-import", {"file": game_zip(files)})


def test_new_cars_and_tracks_come_with_pictures_and_data(api, champ_admin):
    files = {
        "tracks/ks_highlands/ui/layout_long/ui_track.json": ui(
            name="Highlands Long", length="5800"
        ),
        "tracks/ks_highlands/ui/layout_long/outline.png": PNG,
        "tracks/ks_highlands/ui/layout_short/ui_track.json": ui(name="Highlands Short"),
        "tracks/magione/ui/ui_track.json": ui(name="Magione", country="Italy"),
        "tracks/magione/ui/preview.png": PNG,
        "cars/bmw_m3_e30/ui/ui_car.json": ui(name="BMW M3 E30", brand="BMW"),
        "cars/bmw_m3_e30/ui/badge.png": PNG,
        "cars/bmw_m3_e30/preview.jpg": JPEG,
    }
    response = send(api, champ_admin, files)
    assert response.status_code == 200, response.json()
    data = response.json()
    assert sorted(data["new_tracks"]) == ["ks_highlands", "magione"]
    assert sorted(data["new_layouts"]) == [
        "ks_highlands/layout_long",
        "ks_highlands/layout_short",
        "magione",
    ]
    assert data["new_cars"] == ["bmw_m3_e30"]
    highlands = Track.objects.get(key="ks_highlands")
    assert highlands.name == "Highlands"
    assert sorted(highlands.layouts.values_list("name", flat=True)) == ["Long", "Short"]
    magione = Track.objects.get(key="magione")
    assert magione.layouts.get().name == "GP"
    assert magione.layouts.get().preview
    car = Car.objects.get(key="bmw_m3_e30")
    assert (car.name, car.brand) == ("BMW M3 E30", "BMW")
    assert car.badge and car.preview


def test_an_item_that_exists_is_not_added_again(api, champ_admin):
    Car.objects.create(key="bmw_m3_e30", name="My own name")
    data = send(api, champ_admin, {"cars/BMW_M3_E30/ui/ui_car.json": ui(name="BMW")}).json()
    assert data["new_cars"] == []
    assert Car.objects.get().name == "My own name"  # An admin edit stays.


def test_an_unsafe_folder_name_is_ignored(api, champ_admin):
    data = send(api, champ_admin, {"cars/bad name;x/ui/ui_car.json": ui(name="x")}).json()
    assert data["new_cars"] == [] and not Car.objects.exists()


def test_a_driver_cannot_import(api, driver_user):
    assert send(api, driver_user, {"cars/a/ui/ui_car.json": ui(name="A")}).status_code == 403
