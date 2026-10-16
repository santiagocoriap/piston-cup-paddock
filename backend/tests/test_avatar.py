import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.competition.models import ChampionshipMember, SeasonEntry
from apps.identity.models import DriverProfile

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff" + b"0" * 64


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def upload(client, data, name="me.png"):
    return client.post("/api/auth/me/avatar", {"file": SimpleUploadedFile(name, data)})


def test_a_user_sets_shows_and_removes_a_picture(media, client, make_user):
    user = make_user("ana")
    client.force_login(user)
    assert client.get("/api/auth/me").json()["avatar_url"] is None

    first = upload(client, PNG).json()["avatar_url"]
    assert first.startswith(f"/api/auth/avatars/{user.id}?v=")
    picture = client.get(first)
    assert (picture.status_code, picture["Content-Type"]) == (200, "image/png")
    assert picture.content == PNG

    second = upload(client, JPEG, "me.jpg").json()["avatar_url"]
    assert second != first  # A new address, so the browser does not keep the old picture.
    assert client.get(second)["Content-Type"] == "image/jpeg"

    assert client.delete("/api/auth/me/avatar").json()["avatar_url"] is None
    assert client.get(second).status_code == 404


def test_only_a_small_png_or_jpeg_is_a_picture(media, client, make_user):
    client.force_login(make_user("ana"))
    assert upload(client, b"GIF89a" + b"0" * 64, "me.gif").json()["detail"] == "image_not_supported"
    big = PNG + b"0" * (2 * 1024 * 1024)
    assert upload(client, big).json()["detail"] == "image_too_large"


def test_the_entries_show_the_picture_of_the_driver(media, client, make_user, season, car, api):
    user = make_user("ana")
    driver = DriverProfile.objects.create(display_name="Ana", user=user)
    SeasonEntry.objects.create(season=season, driver=driver, car=car, number=7)
    ChampionshipMember.objects.create(
        championship=season.championship, user=user, role=ChampionshipMember.Role.DRIVER
    )
    client.force_login(user)
    url = upload(client, PNG).json()["avatar_url"]
    assert client.get(f"/api/auth/avatars/{user.id}").status_code == 200

    entries = api(user).get(f"/seasons/{season.id}").json()["entries"]
    assert entries[0]["avatar_url"] == url


def test_a_visitor_without_a_session_sees_no_picture(media, client, make_user):
    user = make_user("ana")
    client.force_login(user)
    upload(client, PNG)
    client.logout()
    assert client.get(f"/api/auth/avatars/{user.id}").status_code == 401
