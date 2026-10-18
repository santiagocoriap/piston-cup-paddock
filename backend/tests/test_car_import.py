"""Importar desde el juego: the source, the data folder, the skins, and the class of a car."""

import io
import json
import zipfile

import pytest
from PIL import Image

from apps.catalog.models import Car, CarClass, CarClassMembership, CarSkin
from tests.test_acd import TYRES, pack


def picture(width=1920, height=1080) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(out, "JPEG")
    return out.getvalue()


def archive(files: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as handle:
        for name, data in files.items():
            handle.writestr(name, data)
    buffer.seek(0)
    buffer.name = "game.zip"
    return buffer


def ui(**values) -> bytes:
    return json.dumps(values).encode()


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


def send(api, user, files):
    response = api(user).client.post("/api/catalog/game-import", {"file": archive(files)})
    assert response.status_code == 200, response.content
    return response


def car_files(key="ks_ferrari_488_gt3", **extra) -> dict[str, bytes]:
    return {
        f"cars/{key}/ui/ui_car.json": ui(name="Ferrari 488 GT3", brand="Ferrari", **extra),
        f"cars/{key}/data.acd": pack({"tyres.ini": TYRES}, key),
        f"cars/{key}/skins/00_rosso_scuderia/ui_skin.json": ui(
            skinname="Rosso Scuderia", number="0"
        ),
        f"cars/{key}/skins/00_rosso_scuderia/preview.jpg": picture(),
        f"cars/{key}/skins/01_racing 483/ui_skin.json": ui(skinname="Racing 483", priority=2),
    }


def test_the_data_folder_is_read_and_kept_as_numbers(api, champ_admin):
    send(api, champ_admin, car_files())
    car = Car.objects.get(key="ks_ferrari_488_gt3")
    assert car.data_error == ""
    assert car.data["ini"]["tyres"]["FRONT"]["NAME"] == "Slick Soft"
    assert car.data["ini"]["tyres"]["FRONT"]["PRESSURE_IDEAL"] == 26
    listed = api(champ_admin).get("/catalog/cars").json()[0]
    assert listed["has_data"] and listed["tyres"][0]["short_name"] == "S"
    assert listed["tyres"][0]["front"]["width"] == 0.3
    assert "data" not in listed  # The big JSON has its own address.
    full = api(champ_admin).get(f"/catalog/cars/{car.id}/data").json()
    assert full["ini"]["tyres"]["FRONT"]["WIDTH"] == 0.3


def test_an_archive_that_cannot_be_read_is_reported_not_guessed(api, champ_admin):
    files = car_files()
    files["cars/ks_ferrari_488_gt3/data.acd"] = pack({"tyres.ini": TYRES}, "other_folder")
    send(api, champ_admin, files)
    car = Car.objects.get(key="ks_ferrari_488_gt3")
    assert car.data == {} and car.data_error == "unknown_key"
    assert api(champ_admin).get("/catalog/cars").json()[0]["data_error"] == "unknown_key"


def test_an_unpacked_data_folder_is_read(api, champ_admin):
    files = car_files()
    del files["cars/ks_ferrari_488_gt3/data.acd"]
    files["cars/ks_ferrari_488_gt3/data/tyres.ini"] = TYRES
    send(api, champ_admin, files)
    assert Car.objects.get().data["ini"]["tyres"]["FRONT"]["SHORT_NAME"] == "S"


def test_skins_come_with_a_small_picture(api, champ_admin):
    send(api, champ_admin, car_files())
    skins = {skin.key: skin for skin in CarSkin.objects.all()}
    assert set(skins) == {"00_rosso_scuderia", "01_racing 483"}  # A folder name keeps its spaces.
    red = skins["00_rosso_scuderia"]
    assert (red.name, red.number) == ("Rosso Scuderia", "0")
    assert skins["01_racing 483"].priority == 2 and not skins["01_racing 483"].preview
    assert red.preview.size < 20_000  # Not the 1920x1080 file.
    with Image.open(red.preview.path) as small:
        assert small.format == "WEBP" and max(small.size) <= 640
    response = api(champ_admin).get(f"/catalog/skins/{red.id}/preview")
    assert response.status_code == 200 and response["Content-Type"] == "image/webp"
    listed = api(champ_admin).get("/catalog/cars").json()[0]["skins"]
    assert [s["key"] for s in listed] == ["00_rosso_scuderia", "01_racing 483"]


def test_an_import_twice_keeps_one_skin_and_the_picture(api, champ_admin):
    send(api, champ_admin, car_files())
    only_json = {k: v for k, v in car_files().items() if not k.endswith(".jpg")}
    send(api, champ_admin, only_json)
    assert CarSkin.objects.count() == 2
    assert CarSkin.objects.get(key="00_rosso_scuderia").preview


@pytest.mark.parametrize(
    ("extra", "author", "key", "source"),
    [
        ({"dlc": 1}, "Kunos", "ks_ferrari_488_gt3", "dlc"),
        ({}, "Kunos", "ks_mazda_miata", "base"),
        ({}, "TRR", "TRR_GT3_bmw_m4_gt3", "mod"),
    ],
)
def test_the_source_of_a_car(api, champ_admin, extra, author, key, source):
    files = {f"cars/{key}/ui/ui_car.json": ui(name="Car", author=author)}
    if extra:
        files[f"cars/{key}/ui/dlc_ui_car.json"] = ui(url="http://store.steampowered.com/app/493190")
    send(api, champ_admin, files)
    car = Car.objects.get(key=key)
    assert car.source == source
    assert car.source_url == ("http://store.steampowered.com/app/493190" if extra else "")


def test_the_game_class_makes_a_class_once_and_an_admin_edit_stays(api, champ_admin):
    send(api, champ_admin, car_files(**{"class": "TRRGT3"}))
    car_class = CarClass.objects.get(name="TRRGT3")
    assert list(car_class.memberships.values_list("car__key", flat=True)) == ["ks_ferrari_488_gt3"]
    # The admin moves the car out of the class. A new import must not put it back.
    CarClassMembership.objects.all().update(valid_to="2020-01-01")
    send(api, champ_admin, car_files(**{"class": "TRRGT3"}))
    assert CarClassMembership.objects.count() == 1
    assert CarClass.objects.count() == 1


def test_a_note_after_a_tyre_number_does_not_break_the_list(api, champ_admin):
    messy = TYRES.replace(b"WIDTH=0.3", b"WIDTH=0.3\t  (/129)")
    assert messy != TYRES
    send(
        api,
        champ_admin,
        {"cars/mod_car/ui/ui_car.json": ui(name="Mod"), "cars/mod_car/data/tyres.ini": messy},
    )
    listed = api(champ_admin).get("/catalog/cars").json()[0]
    assert listed["tyres"][0]["front"]["width"] == 0.3
    # Data saved by the older parser still holds the text.
    Car.objects.update(data={"ini": {"tyres": {"FRONT": {"NAME": "S", "WIDTH": "0.215\t (/129)"}}}})
    assert api(champ_admin).get("/catalog/cars").json()[0]["tyres"][0]["front"]["width"] == 0.215


def test_wear_summary_gives_the_wear_where_grip_falls_under_each_level():
    from apps.catalog.car_data import tyre_compounds, wear_summary

    summary = wear_summary([[0, 100], [10, 100], [20, 90], [40, 70]])
    assert summary["x_95"] == 15 and summary["x_90"] == 20 and summary["x_80"] == 30
    assert summary["end_x"] == 40 and summary["end_grip"] == 0.7
    assert wear_summary([[0, 100], [10, 98]])["x_95"] is None
    assert wear_summary([[0, 0], [10, 0]]) is None and wear_summary([[0, 1]]) is None
    data = {
        "ini": {"tyres": {"FRONT": {"NAME": "Street", "WEAR_CURVE": "Hard_Front.lut"}}},
        "lut": {"hard_front": [[0, 1], [50, 0.8]]},
    }
    assert tyre_compounds(data)[0]["front"]["wear"]["x_80"] == 50
