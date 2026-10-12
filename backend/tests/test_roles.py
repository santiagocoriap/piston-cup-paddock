"""Steward and custom roles: selected capabilities in one championship only."""

import pytest

from apps.competition.models import ChampionshipMember, ChampionshipRole, Round, SeasonEntry
from apps.competition.permissions import capabilities
from apps.identity.models import DriverProfile


@pytest.fixture
def raced(api, champ_admin, season, layout, car):
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
        )
        for n in (1, 2)
    ]
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    admin = api(champ_admin)
    admin.post(f"/rounds/{round_.id}/restarts", {"reason": "first_lap_crash"})
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
    return round_, entries


def member(api, champ_admin, championship, user, role, custom_role_id=None):
    body = {"user_id": user.id, "role": role}
    if custom_role_id:
        body["custom_role_id"] = custom_role_id
    return api(champ_admin).put(f"/championships/{championship.id}/members", body)


def test_steward_reviews_restarts_and_penalties_only(
    api, champ_admin, championship, make_user, raced
):
    round_, entries = raced
    steward = make_user("steward")
    member(api, champ_admin, championship, steward, "steward")
    client = api(steward)

    detail = client.get(f"/rounds/{round_.id}").json()
    assert detail["capabilities"] == ["penalties", "restarts"]
    assert detail["can_manage"] is False
    me = client.get("/auth/me").json()
    assert (me["can_admin"], me["can_manage"]) == (True, False)

    restart_id = client.get(f"/rounds/{round_.id}/restarts").json()["restarts"][0]["id"]
    response = client.put(
        f"/restarts/{restart_id}/responsibility",
        {"responsibility": "racing_incident", "review_status": "confirmed", "reason": "Ok"},
    )
    assert response.status_code == 200
    penalty = client.post(
        f"/rounds/{round_.id}/penalties",
        {"entry_id": entries[0].id, "kind": "points", "value": 2, "reason": "Contacto"},
    )
    assert penalty.status_code == 200

    # No results, no approval, no seasons, no members.
    assert client.post(f"/rounds/{round_.id}/result/approve").status_code == 403
    assert client.get(f"/rounds/{round_.id}/imports").status_code == 403
    assert client.get(f"/championships/{championship.id}/members").status_code == 403


def test_custom_role_gets_selected_capabilities(api, champ_admin, championship, make_user, raced):
    round_, _ = raced
    created = api(champ_admin).post(
        f"/championships/{championship.id}/roles",
        {"name": "Cronista", "capabilities": ["reports", "results"]},
    )
    assert created.status_code == 201
    role_id = created.json()["id"]
    writer = make_user("writer")
    assert member(api, champ_admin, championship, writer, "custom", role_id).status_code == 200
    client = api(writer)
    assert client.get(f"/rounds/{round_.id}").json()["capabilities"] == ["reports", "results"]
    assert client.post(f"/rounds/{round_.id}/result/approve").status_code == 200
    restart_id = client.get(f"/rounds/{round_.id}/restarts").json()["restarts"][0]["id"]
    response = client.put(
        f"/restarts/{restart_id}/responsibility",
        {"responsibility": "unknown", "review_status": "pending", "reason": "x"},
    )
    assert response.status_code == 403

    # An admin changes the role, and the member loses the capability.
    api(champ_admin).put(f"/roles/{role_id}", {"name": "Cronista", "capabilities": ["reports"]})
    assert client.get(f"/rounds/{round_.id}").json()["capabilities"] == ["reports"]


def test_custom_role_has_no_access_to_other_championships(
    api, champ_admin, championship, other_championship, make_user, league_admin
):
    role = ChampionshipRole.objects.create(
        championship=other_championship, name="Other", capabilities=["results"]
    )
    user = make_user("someone")
    # A role of another championship cannot be given here.
    response = member(api, champ_admin, championship, user, "custom", role.id)
    assert response.status_code == 404
    # A member row with a wrong role (for example from the database) still gives nothing.
    ChampionshipMember.objects.create(
        championship=championship, user=user, role="custom", custom_role=role
    )
    assert capabilities(user, championship) == set()
    assert capabilities(user, other_championship) == set()


def test_championship_admin_cannot_make_links_for_a_steward(
    api, champ_admin, championship, make_user
):
    steward = make_user("steward")
    member(api, champ_admin, championship, steward, "steward")
    response = api(champ_admin).post(f"/accounts/{steward.id}/link")
    assert response.status_code == 403
