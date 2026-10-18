import pytest
from django.test import Client

from apps.identity.models import User

PASSWORD = "test-password-8472"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="driver", password=PASSWORD)


def csrf_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get("/api/auth/csrf")
    assert response.status_code == 204
    return client, client.cookies["csrftoken"].value


def login(client: Client, token: str, password: str = PASSWORD):
    return client.post(
        "/api/auth/login",
        {"username": "driver", "password": password},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


def test_login_with_correct_password_starts_a_session(user):
    client, token = csrf_client()
    response = login(client, token)
    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": "driver",
        "language": "es",
        "is_admin": False,
        "is_platform_admin": False,
        "can_admin": False,
        "can_manage": False,
        "timezone": "",
        "avatar_url": None,
    }
    assert client.get("/api/auth/me").json()["username"] == "driver"


def test_login_with_wrong_password_fails(user):
    client, token = csrf_client()
    assert login(client, token, password="wrong").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_without_csrf_token_fails(user):
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/api/auth/login",
        {"username": "driver", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403


def test_logout_ends_the_session(user):
    client, token = csrf_client()
    login(client, token)
    token = client.cookies["csrftoken"].value
    assert client.post("/api/auth/logout", headers={"X-CSRFToken": token}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_database_stores_only_a_password_hash(user):
    user.refresh_from_db()
    assert PASSWORD not in user.password
    assert user.check_password(PASSWORD)


def test_championship_admin_can_use_the_admin_mode(api, champ_admin):
    assert api(champ_admin).get("/auth/me").json()["can_admin"] is True


def test_driver_cannot_use_the_admin_mode(api, driver_user):
    assert api(driver_user).get("/auth/me").json()["can_admin"] is False


def test_user_changes_language_and_timezone(api, driver_user):
    client = api(driver_user)
    response = client.client.patch(
        "/api/auth/me",
        {"language": "en", "timezone": "Europe/Madrid"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert (response.json()["language"], response.json()["timezone"]) == ("en", "Europe/Madrid")
    assert client.get("/auth/me").json()["language"] == "en"


def test_unknown_timezone_is_refused(api, driver_user):
    response = api(driver_user).client.patch(
        "/api/auth/me", {"timezone": "Mars/Olympus"}, content_type="application/json"
    )
    assert response.json()["detail"] == "bad_timezone"


def test_empty_timezone_means_the_browser_timezone(api, driver_user):
    response = api(driver_user).client.patch(
        "/api/auth/me", {"timezone": ""}, content_type="application/json"
    )
    assert response.json()["timezone"] == ""


def test_round_and_season_give_the_event_timezone(api, champ_admin, season, layout):
    from apps.competition.models import Round

    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    client = api(champ_admin)
    assert client.get(f"/rounds/{round_.id}").json()["event_timezone"] == (
        "America/Argentina/Buenos_Aires"
    )
    assert client.get(f"/seasons/{season.id}").json()["event_timezone"] == (
        "America/Argentina/Buenos_Aires"
    )


def test_round_gives_the_championship_for_the_breadcrumbs(api, champ_admin, season, layout):
    from apps.competition.models import Round

    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    detail = api(champ_admin).get(f"/rounds/{round_.id}").json()
    assert (detail["championship_id"], detail["championship_name"]) == (
        season.championship_id,
        season.championship.name,
    )
