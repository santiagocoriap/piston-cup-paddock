from datetime import timedelta

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.identity.models import LoginFailure, User
from apps.identity.throttle import client_ip

PASSWORD = "right-password-4821"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="ana", password=PASSWORD)


def attempt(password, username="ana", ip="203.0.113.5", forwarded=None):
    client = Client(REMOTE_ADDR=ip)
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return client.post(
        "/api/auth/login",
        {"username": username, "password": password},
        content_type="application/json",
        headers=headers,
    )


def test_five_wrong_passwords_block_the_username(user):
    for _ in range(5):
        assert attempt("wrong").status_code == 401
    blocked = attempt(PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "too_many_attempts"


def test_block_ends_after_15_minutes(user):
    for _ in range(5):
        attempt("wrong")
    LoginFailure.objects.update(failed_at=timezone.now() - timedelta(minutes=16))
    assert attempt(PASSWORD).status_code == 200


def test_correct_login_resets_the_count(user):
    for _ in range(4):
        attempt("wrong")
    assert attempt(PASSWORD).status_code == 200
    for _ in range(4):
        assert attempt("wrong").status_code == 401
    assert attempt(PASSWORD).status_code == 200


def test_username_is_counted_without_letter_case(user):
    for _ in range(5):
        attempt("wrong", username="ANA")
    assert attempt(PASSWORD, username="ana").status_code == 429


def test_twenty_wrong_passwords_block_the_ip_address(user):
    for n in range(20):
        attempt("wrong", username=f"guess{n}")
    assert attempt(PASSWORD).status_code == 429
    assert attempt(PASSWORD, ip="198.51.100.7").status_code == 200


def test_the_database_keeps_no_password(user):
    attempt("secret-guess-123")
    stored = LoginFailure.objects.get()
    assert "secret-guess-123" not in str(vars(stored))


class TestClientIp:
    def request(self, remote, forwarded=None):
        meta = {"REMOTE_ADDR": remote}
        if forwarded:
            meta["HTTP_X_FORWARDED_FOR"] = forwarded
        return RequestFactory().get("/", **meta)

    def test_without_a_proxy_the_header_is_ignored(self, settings):
        settings.TRUSTED_PROXY_COUNT = 0
        assert client_ip(self.request("203.0.113.5", "1.2.3.4")) == "203.0.113.5"

    def test_behind_one_proxy_the_last_address_counts(self, settings):
        settings.TRUSTED_PROXY_COUNT = 1
        # The client sent "1.2.3.4". The proxy added the real address at the end.
        request = self.request("10.0.0.2", "1.2.3.4, 203.0.113.5")
        assert client_ip(request) == "203.0.113.5"

    def test_fake_header_cannot_dodge_the_ip_limit(self, settings, user):
        settings.TRUSTED_PROXY_COUNT = 1
        for n in range(20):
            attempt("wrong", username=f"g{n}", ip="10.0.0.2", forwarded=f"9.9.9.{n}, 203.0.113.5")
        response = attempt(PASSWORD, ip="10.0.0.2", forwarded="8.8.8.8, 203.0.113.5")
        assert response.status_code == 429
