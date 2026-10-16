import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.catalog.game_images import GameImagesError, import_game_images, open_source
from apps.catalog.models import Car, Track, TrackLayout

PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
JPEG = b"\xff\xd8\xff" + b"jpeg-body"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def content(tmp_path):
    """A small copy of the Assetto Corsa content folder."""
    root = tmp_path / "assettocorsa" / "content"
    layout = root / "tracks" / "ks_highlands" / "ui" / "layout_long"
    layout.mkdir(parents=True)
    (layout / "outline.png").write_bytes(PNG)
    (layout / "preview.png").write_bytes(PNG)
    # The game writes loose JSON: a BOM and a raw tab inside a string.
    (layout / "ui_track.json").write_bytes(
        '﻿{"name": "Highlands Long", "length": "12191", "country": "Sco\ttland"}'.encode()
    )
    single = root / "tracks" / "magione" / "ui"
    single.mkdir(parents=True)
    (single / "outline.png").write_bytes(PNG)
    car = root / "cars" / "TRR_LMDH_Acura_ARX-06"
    (car / "ui").mkdir(parents=True)
    (car / "ui" / "badge.png").write_bytes(PNG)
    (car / "ui" / "ui_car.json").write_text('{"brand": "Acura", "author": "TRR"}')
    for skin in ("b_skin", "a_skin"):
        (car / "skins" / skin).mkdir(parents=True)
        (car / "skins" / skin / "preview.jpg").write_bytes(JPEG + skin.encode())
    return root


@pytest.fixture
def magione(db):
    track = Track.objects.create(key="magione", name="Magione")
    return TrackLayout.objects.create(track=track, key="", name="GP")


def test_folder_import_copies_maps_pictures_and_game_text(layout, magione, car, content):
    report = import_game_images(open_source(content.parent))

    assert report.layouts == ["ks_highlands/layout_long", "magione"]
    assert report.cars == ["trr_lmdh_acura_arx-06"]
    layout.refresh_from_db()
    assert layout.outline.read() == PNG
    assert (layout.length_m, layout.country) == (12191, "Sco\ttland")
    # The track gets the country of its layout.
    layout.track.refresh_from_db()
    assert layout.track.country == "Sco\ttland"
    magione.refresh_from_db()
    assert magione.outline and not magione.preview
    car.refresh_from_db()
    # Folder names match without case. The first skin in name order gives the picture.
    assert car.preview.read() == JPEG + b"a_skin"
    assert (car.brand, car.author) == ("Acura", "TRR")


def test_missing_folders_are_reported_and_keep_old_values(layout, car, tmp_path):
    (tmp_path / "content" / "tracks").mkdir(parents=True)
    report = import_game_images(open_source(tmp_path))
    assert report.missing_layouts == ["ks_highlands/layout_long"]
    assert report.missing_cars == ["trr_lmdh_acura_arx-06"]


def test_a_file_that_is_not_an_image_is_ignored(layout, content):
    (content / "tracks" / "ks_highlands" / "ui" / "layout_long" / "outline.png").write_bytes(
        b"<svg onload=alert(1)>"
    )
    import_game_images(open_source(content))
    layout.refresh_from_db()
    assert not layout.outline
    assert layout.preview


def test_a_folder_without_tracks_or_cars_is_refused(tmp_path):
    with pytest.raises(GameImagesError, match="not_a_content_folder"):
        open_source(tmp_path)


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_admin_uploads_a_zip_and_drivers_see_the_pictures(api, champ_admin, me_driver, layout, car):
    data = _zip(
        {
            "content/tracks/ks_highlands/ui/layout_long/outline.png": PNG,
            "cars/trr_lmdh_acura_arx-06/preview.jpg": JPEG,
            "../../etc/passwd": b"x",
        }
    )
    response = api(champ_admin).client.post(
        "/api/catalog/game-images", {"file": SimpleUploadedFile("images.zip", data)}
    )
    assert response.status_code == 200, response.json()
    assert response.json()["layouts"] == ["ks_highlands/layout_long"]

    image = api(me_driver).get(f"/catalog/layouts/{layout.id}/images/outline")
    assert image.status_code == 200
    assert image["Content-Type"] == "image/png"
    assert image["X-Content-Type-Options"] == "nosniff"
    assert b"".join(image.streaming_content) == PNG
    assert api(me_driver).get(f"/catalog/cars/{car.id}/images/preview").status_code == 200
    assert api(me_driver).get(f"/catalog/cars/{car.id}/images/badge").status_code == 404
    tracks = api(me_driver).get("/catalog/tracks").json()
    assert tracks[0]["layouts"][0]["has_outline"] is True


def test_a_driver_cannot_upload_or_read_the_needed_list(api, me_driver):
    upload = api(me_driver).client.post(
        "/api/catalog/game-images", {"file": SimpleUploadedFile("x.zip", _zip({}))}
    )
    assert upload.status_code == 403
    assert api(me_driver).get("/catalog/game-images/needed").status_code == 403


def test_a_broken_zip_is_refused(api, champ_admin):
    response = api(champ_admin).client.post(
        "/api/catalog/game-images", {"file": SimpleUploadedFile("x.zip", b"not a zip")}
    )
    assert (response.status_code, response.json()["detail"]) == (400, "bad_zip")


def test_needed_list_names_every_layout_and_car(api, champ_admin, layout, magione, car):
    assert api(champ_admin).get("/catalog/game-images/needed").json() == {
        "tracks": [
            {"track": "ks_highlands", "layout": "layout_long"},
            {"track": "magione", "layout": ""},
        ],
        "cars": ["trr_lmdh_acura_arx-06"],
    }


def test_command_imports_a_folder(layout, content, capsys):
    call_command("import_game_images", str(content))
    assert "Layouts with images: 1" in capsys.readouterr().out
    assert TrackLayout.objects.get().outline
    assert not Car.objects.exists()


@pytest.fixture
def me_driver(make_user):
    return make_user("driver")
