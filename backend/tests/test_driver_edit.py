"""An admin changes the name and the Steam ID of a driver."""

from apps.identity.models import DriverProfile


def test_a_league_admin_changes_the_name_and_the_steam_id(api, league_admin):
    ana = DriverProfile.objects.create(display_name="Ana", steam_guid="76561190000000001")
    DriverProfile.objects.create(display_name="Bob", steam_guid="76561190000000002")
    client = api(league_admin)
    changed = client.patch(
        f"/drivers/{ana.id}", {"display_name": "Ana Torres", "steam_guid": "76561190000000009"}
    )
    assert changed.status_code == 200
    assert (changed.json()["display_name"], changed.json()["steam_guid"]) == (
        "Ana Torres",
        "76561190000000009",
    )
    taken = client.patch(f"/drivers/{ana.id}", {"steam_guid": "76561190000000002"})
    assert taken.status_code == 409 and taken.json()["detail"] == "steam_guid_exists"
    assert client.patch(f"/drivers/{ana.id}", {"steam_guid": "123"}).status_code == 422
    removed = client.patch(f"/drivers/{ana.id}", {"steam_guid": ""}).json()
    assert removed["steam_guid"] is None


def test_a_championship_admin_cannot_take_the_steam_id_of_a_driver(api, champ_admin, driver_user):
    ana = DriverProfile.objects.create(display_name="Ana", steam_guid="76561190000000001")
    new = DriverProfile.objects.create(display_name="Nuevo")
    client = api(champ_admin)
    # The name, and a first Steam ID for a driver with none: yes.
    assert client.patch(f"/drivers/{ana.id}", {"display_name": "Ana T"}).status_code == 200
    first = client.patch(f"/drivers/{new.id}", {"steam_guid": "76561190000000005"})
    assert first.status_code == 200
    # A change or a removal of a Steam ID: only a league admin.
    other = client.patch(f"/drivers/{ana.id}", {"steam_guid": "76561190000000009"})
    assert other.status_code == 403
    assert client.patch(f"/drivers/{ana.id}", {"steam_guid": ""}).status_code == 403
    ana.refresh_from_db()
    assert ana.steam_guid == "76561190000000001"
    assert api(driver_user).patch(f"/drivers/{ana.id}", {"display_name": "X"}).status_code == 403
