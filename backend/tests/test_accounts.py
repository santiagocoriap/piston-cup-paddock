from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEntry
from apps.competition.models import ChampionshipMember
from apps.identity.models import AccountLink, DriverProfile, User

NEW_PASSWORD = "brand-new-pass-77"


def token_of(response) -> str:
    return response.json()["link_path"].split("#", 1)[1]


def accept(token, password=NEW_PASSWORD, again=None):
    client = Client()
    response = client.post(
        "/api/auth/invite/accept",
        {"token": token, "password": password, "password_again": again or password},
        content_type="application/json",
    )
    return client, response


def test_league_admin_makes_an_account_with_a_driver_and_a_role(api, league_admin, championship):
    driver = DriverProfile.objects.create(display_name="Bing")
    response = api(league_admin).post(
        "/accounts",
        {
            "username": "bing",
            "driver_id": driver.id,
            "championship_id": championship.id,
            "role": "driver",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["link_path"].startswith("/invite#")
    assert data["account"]["driver_name"] == "Bing"
    assert data["account"]["championships"] == ["LMDh (driver)"]
    assert data["account"]["has_password"] is False
    user = User.objects.get(username="bing")
    assert ChampionshipMember.objects.filter(user=user, championship=championship).exists()


def test_invite_link_sets_the_password_and_signs_in(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    check = Client().post(
        "/api/auth/invite/check", {"token": token}, content_type="application/json"
    )
    assert check.json() == {"username": "bing", "purpose": "invite"}

    client, response = accept(token)
    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "bing"
    assert User.objects.get(username="bing").check_password(NEW_PASSWORD)


def test_link_works_only_one_time(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    accept(token)
    _, again = accept(token, password="other-pass-9911")
    assert again.json()["detail"] == "link_not_valid"


def test_link_ends_after_seven_days(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    AccountLink.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    _, response = accept(token)
    assert response.json()["detail"] == "link_not_valid"


def test_database_keeps_only_a_hash_of_the_token(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    link = AccountLink.objects.get()
    assert token not in link.token_hash
    assert len(link.token_hash) == 64


def test_passwords_must_match_and_be_valid(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    _, differ = accept(token, again="something-else-1")
    assert differ.json()["detail"] == "passwords_differ"
    _, short = accept(token, password="abc")
    assert short.json()["detail"] == "weak_password"
    assert short.json()["messages"]


def test_reset_link_replaces_the_old_links(api, league_admin):
    admin = api(league_admin)
    first = token_of(admin.post("/accounts", {"username": "bing"}))
    accept(first)
    user = User.objects.get(username="bing")
    old = token_of(admin.post(f"/accounts/{user.id}/link"))
    new = token_of(admin.post(f"/accounts/{user.id}/link"))
    _, refused = accept(old, password="reset-pass-3301")
    assert refused.json()["detail"] == "link_not_valid"
    _, ok = accept(new, password="reset-pass-3301")
    assert ok.status_code == 200
    assert AccountLink.objects.filter(user=user, purpose="reset").count() == 2


def test_championship_admin_makes_accounts_only_in_own_championship(
    api, champ_admin, championship, other_championship
):
    client = api(champ_admin)
    assert client.post("/accounts", {"username": "x"}).json()["detail"] == "championship_required"
    other = client.post("/accounts", {"username": "y", "championship_id": other_championship.id})
    assert other.status_code == 403
    own = client.post("/accounts", {"username": "z", "championship_id": championship.id})
    assert own.status_code == 201


def test_driver_cannot_make_accounts(api, driver_user):
    assert api(driver_user).post("/accounts", {"username": "x"}).status_code == 403


def test_user_name_must_be_new(api, league_admin, make_user):
    make_user("Bing")
    assert api(league_admin).post("/accounts", {"username": "bing"}).json()["detail"] == (
        "username_exists"
    )


def test_user_changes_the_password(api, make_user):
    user = make_user("bing")  # Password: unused-pass-1234
    client = api(user)
    wrong = client.post(
        "/auth/password", {"current": "nope", "new": NEW_PASSWORD, "new_again": NEW_PASSWORD}
    )
    assert wrong.json()["detail"] == "wrong_current_password"
    ok = client.post(
        "/auth/password",
        {"current": "unused-pass-1234", "new": NEW_PASSWORD, "new_again": NEW_PASSWORD},
    )
    assert ok.status_code == 204
    assert client.get("/auth/me").status_code == 200  # The session stays.
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_audit_has_no_token_and_no_password(api, league_admin):
    token = token_of(api(league_admin).post("/accounts", {"username": "bing"}))
    accept(token)
    text = str(list(AuditEntry.objects.values("params", "changes", "reason")))
    assert token not in text
    assert NEW_PASSWORD not in text
    actions = list(AuditEntry.objects.order_by("id").values_list("action", flat=True))
    assert actions == ["account.created", "account.link_created", "account.password_set"]


@pytest.mark.parametrize("bad", ["", "a b", "x/y"])
def test_user_name_format(api, league_admin, bad):
    assert api(league_admin).post("/accounts", {"username": bad}).status_code == 422
