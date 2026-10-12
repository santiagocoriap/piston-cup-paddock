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
        "can_admin": False,
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
