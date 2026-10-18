import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEntry

PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
JPEG = b"\xff\xd8\xff" + b"jpeg-body"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def upload(client, path, data, name="picture"):
    return client.client.post(f"/api{path}", {"file": SimpleUploadedFile(name, data)})


def patch(client, path, data):
    return client.client.patch(f"/api{path}", data, content_type="application/json")


def test_an_admin_renames_a_track_a_layout_and_a_car(api, champ_admin, layout, car):
    client = api(champ_admin)
    assert (
        patch(client, f"/catalog/tracks/{layout.track_id}", {"name": "Highlands GP"}).status_code
        == 200
    )
    assert (
        patch(client, f"/catalog/layouts/{layout.id}", {"name": "Largo"}).json()["name"] == "Largo"
    )
    assert patch(client, f"/catalog/cars/{car.id}", {"name": "Acura"}).json()["name"] == "Acura"

    tracks = client.get("/catalog/tracks").json()
    assert (tracks[0]["name"], tracks[0]["layouts"][0]["name"]) == ("Highlands GP", "Largo")
    renamed = AuditEntry.objects.get(action="car.renamed")
    assert renamed.changes == [{"field": "name", "old": "Acura ARX-06", "new": "Acura"}]


def test_an_admin_uploads_a_jpeg_map_and_removes_it(api, champ_admin, layout):
    client = api(champ_admin)
    response = upload(client, f"/catalog/layouts/{layout.id}/images/outline", JPEG)
    assert response.status_code == 200, response.json()
    assert response.json()["has_outline"] is True

    image = client.get(f"/catalog/layouts/{layout.id}/images/outline")
    assert image["Content-Type"] == "image/jpeg"
    assert b"".join(image.streaming_content) == JPEG

    removed = client.client.delete(f"/api/catalog/layouts/{layout.id}/images/outline")
    assert removed.json()["has_outline"] is False
    assert client.get(f"/catalog/layouts/{layout.id}/images/outline").status_code == 404


def test_an_admin_uploads_a_car_badge(api, champ_admin, car):
    client = api(champ_admin)
    assert upload(client, f"/catalog/cars/{car.id}/images/badge", PNG).json()["has_badge"] is True
    assert client.get(f"/catalog/cars/{car.id}/images/badge")["Content-Type"] == "image/png"


def test_only_a_png_or_a_jpeg_of_at_most_5_mb_is_accepted(api, champ_admin, car):
    client = api(champ_admin)
    svg = upload(client, f"/catalog/cars/{car.id}/images/preview", b"<svg onload=alert(1)>")
    assert svg.status_code == 400
    assert svg.json()["detail"] == "image_not_supported"
    big = upload(client, f"/catalog/cars/{car.id}/images/preview", PNG + b"0" * (5 * 1024 * 1024))
    assert big.json()["detail"] == "image_too_large"
    assert upload(client, f"/catalog/cars/{car.id}/images/other", PNG).status_code == 404


def test_a_driver_cannot_change_the_catalog(api, make_user, layout, car):
    driver = api(make_user("driver"))
    assert patch(driver, f"/catalog/cars/{car.id}", {"name": "X"}).status_code == 403
    assert upload(driver, f"/catalog/layouts/{layout.id}/images/preview", PNG).status_code == 403


def test_an_admin_sets_the_country_of_a_track_and_a_rename_keeps_it(api, champ_admin, layout):
    client = api(champ_admin)
    path = f"/catalog/tracks/{layout.track_id}"
    assert (
        patch(client, path, {"name": "Highlands", "country": " Escocia "}).json()["country"]
        == "Escocia"
    )
    assert patch(client, path, {"name": "Highlands GP"}).json()["country"] == "Escocia"
    assert patch(client, path, {"name": "Highlands GP", "country": ""}).json()["country"] == ""
    created = client.post(
        "/catalog/tracks", {"key": "magione", "name": "Magione", "country": "Italia"}
    )
    assert created.json()["country"] == "Italia"
