import pytest
from django.core.management import CommandError, call_command

from apps.identity.models import User


@pytest.fixture(autouse=True)
def admin_password(monkeypatch):
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", "first-admin-pass-5531")


@pytest.mark.django_db
def test_command_makes_an_admin_account():
    call_command("create_first_admin", username="santi")
    admin = User.objects.get(username="santi")
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("first-admin-pass-5531")


@pytest.mark.django_db
def test_command_rejects_a_weak_password(monkeypatch):
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", "123")
    with pytest.raises(CommandError):
        call_command("create_first_admin", username="santi")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_command_with_if_missing_keeps_an_existing_account():
    User.objects.create_user(username="santi", password="other-pass-9921")
    call_command("create_first_admin", username="santi", if_missing=True)
    assert User.objects.get(username="santi").check_password("other-pass-9921")


@pytest.mark.django_db
def test_prompt_asks_for_the_password_two_times(monkeypatch):
    monkeypatch.delenv("FIRST_ADMIN_PASSWORD")
    answers = iter(["typed-pass-7741", "typed-pass-7741"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    call_command("create_first_admin", username="santi")
    assert User.objects.get(username="santi").check_password("typed-pass-7741")


@pytest.mark.django_db
def test_different_passwords_make_no_account(monkeypatch):
    monkeypatch.delenv("FIRST_ADMIN_PASSWORD")
    answers = iter(["typed-pass-7741", "typed-pass-7742"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    with pytest.raises(CommandError, match="not the same"):
        call_command("create_first_admin", username="santi")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_common_password_is_allowed(monkeypatch):
    monkeypatch.setenv("FIRST_ADMIN_PASSWORD", "password123")
    call_command("create_first_admin", username="santi")
    assert User.objects.get(username="santi").check_password("password123")
