"""Teams of a league: the entry form lists them, and a new name becomes a team."""

import pytest

from apps.competition.models import SeasonEntry, Team
from apps.identity.models import DriverProfile


@pytest.fixture
def drivers(db):
    return [DriverProfile.objects.create(display_name=name) for name in ("Ana", "Bruno")]


def test_a_new_team_name_becomes_a_team_of_the_league(api, champ_admin, season, car, drivers):
    admin = api(champ_admin)
    body = {"driver_id": drivers[0].id, "car_id": car.id, "number": 1, "team": "  Rojo  Racing "}
    assert admin.post(f"/seasons/{season.id}/entries", body).json()["team"] == "Rojo Racing"
    body = {"driver_id": drivers[1].id, "car_id": car.id, "number": 2, "team": "rojo racing"}
    # The same team in other letters: the spelling of the league stays.
    assert admin.post(f"/seasons/{season.id}/entries", body).json()["team"] == "Rojo Racing"
    assert [t["name"] for t in admin.get(f"/seasons/{season.id}/teams").json()] == ["Rojo Racing"]


def test_the_admin_makes_and_removes_teams_and_changes_an_entry(
    api, champ_admin, driver_user, season, car, drivers
):
    admin = api(champ_admin)
    team = admin.post(f"/seasons/{season.id}/teams", {"name": "Azul"}).json()
    entry = SeasonEntry.objects.create(season=season, driver=drivers[0], car=car, number=5)
    changed = admin.client.patch(
        f"/api/entries/{entry.id}", {"team": "azul", "number": 7}, content_type="application/json"
    ).json()
    assert (changed["team"], changed["number"]) == ("Azul", 7)
    assert api(driver_user).client.delete(f"/api/teams/{team['id']}").status_code == 403
    assert admin.client.delete(f"/api/teams/{team['id']}").status_code == 204
    assert not Team.objects.exists()
    entry.refresh_from_db()
    assert entry.team == "Azul"  # The entry keeps its team name.
