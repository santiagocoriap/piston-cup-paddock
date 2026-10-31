"""An admin changes the name and the Steam ID of a driver."""

from apps.identity.models import DriverProfile


def test_an_admin_changes_the_name_and_the_steam_id(api, champ_admin, driver_user):
    ana = DriverProfile.objects.create(display_name="Ana", steam_guid="76561190000000001")
    DriverProfile.objects.create(display_name="Bob", steam_guid="76561190000000002")
    client = api(champ_admin)
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
    refused = api(driver_user).patch(f"/drivers/{ana.id}", {"display_name": "X"})
    assert refused.status_code == 403
