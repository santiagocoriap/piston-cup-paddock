import pytest

from apps.competition.models import Round
from apps.identity.models import DriverProfile

ROUND_DATE = "2026-10-18T21:30:00-03:00"


def test_league_admin_makes_a_league_championship_and_season(api, league_admin):
    client = api(league_admin)
    league = client.post("/leagues", {"name": "Piston Cup"})
    assert league.status_code == 201
    championship = client.post(f"/leagues/{league.json()['id']}/championships", {"name": "LMDh"})
    assert championship.status_code == 201
    season = client.post(
        f"/championships/{championship.json()['id']}/seasons",
        {"name": "2026", "planned_round_count": 8},
    )
    assert season.status_code == 201
    assert season.json()["planned_round_count"] == 8


def test_league_list_shows_the_championships_and_their_season_count(api, league_admin, season):
    leagues = api(league_admin).get("/leagues").json()
    league = next(item for item in leagues if item["id"] == season.championship.league_id)
    assert league["championships"] == [
        {"id": season.championship_id, "name": season.championship.name, "season_count": 1}
    ]


def test_new_league_has_no_championships(api, league_admin):
    response = api(league_admin).post("/leagues", {"name": "Empty League"})
    assert response.json()["championships"] == []


def test_duplicate_season_name_gives_conflict(api, league_admin, season):
    response = api(league_admin).post(
        f"/championships/{season.championship_id}/seasons",
        {"name": "2026", "planned_round_count": 8},
    )
    assert response.status_code == 409


def test_driver_profile_without_account_links_to_an_account_later(api, league_admin, make_user):
    client = api(league_admin)
    created = client.post("/drivers", {"display_name": "Bing", "steam_guid": "76561190000000001"})
    assert created.status_code == 201
    assert created.json()["user_id"] is None

    account = make_user("bing")
    linked = client.post(f"/drivers/{created.json()['id']}/link", {"user_id": account.id})
    assert linked.status_code == 200
    assert linked.json()["username"] == "bing"


def test_one_account_cannot_own_two_driver_profiles(api, league_admin, make_user):
    account = make_user("bing")
    DriverProfile.objects.create(display_name="Bing", user=account)
    second = DriverProfile.objects.create(display_name="Bing 2")
    response = api(league_admin).post(f"/drivers/{second.id}/link", {"user_id": account.id})
    assert response.status_code == 409


def test_steam_guid_must_have_17_digits(api, league_admin):
    response = api(league_admin).post("/drivers", {"display_name": "X", "steam_guid": "123"})
    assert response.status_code == 422


def test_admin_adds_season_entries_with_car_number_and_team(api, champ_admin, season, car):
    driver = DriverProfile.objects.create(display_name="Bing")
    client = api(champ_admin)
    response = client.post(
        f"/seasons/{season.id}/entries",
        {"driver_id": driver.id, "car_id": car.id, "number": 93, "team": "Meyer Shank"},
    )
    assert response.status_code == 201
    entries = client.get(f"/seasons/{season.id}").json()["entries"]
    assert entries == [response.json()]
    assert entries[0]["car_name"] == "Acura ARX-06"


def test_two_entries_cannot_share_a_number(api, champ_admin, season, car):
    first = DriverProfile.objects.create(display_name="A")
    second = DriverProfile.objects.create(display_name="B")
    client = api(champ_admin)
    path = f"/seasons/{season.id}/entries"
    ok = client.post(path, {"driver_id": first.id, "car_id": car.id, "number": 7})
    clash = client.post(path, {"driver_id": second.id, "car_id": car.id, "number": 7})
    assert (ok.status_code, clash.status_code) == (201, 409)


def test_admin_adds_rounds_with_layout_date_and_manual_origin(api, champ_admin, season, layout):
    client = api(champ_admin)
    path = f"/seasons/{season.id}/rounds"
    first = client.post(path, {"track_layout_id": layout.id, "scheduled_at": ROUND_DATE})
    client.post(path, {"track_layout_id": layout.id, "scheduled_at": ROUND_DATE})
    assert first.status_code == 201
    assert first.json()["origin"] == Round.Origin.MANUAL
    assert first.json()["layout_name"] == "Long"
    assert first.json()["scheduled_at"].startswith("2026-10-19T00:30:00")
    rounds = client.get(f"/seasons/{season.id}").json()["rounds"]
    assert [r["number"] for r in rounds] == [1, 2]


def test_round_date_needs_a_timezone(api, champ_admin, season, layout):
    response = api(champ_admin).post(
        f"/seasons/{season.id}/rounds",
        {"track_layout_id": layout.id, "scheduled_at": "2026-10-18T21:30:00"},
    )
    assert response.status_code == 422


def test_admin_adds_tracks_layouts_and_cars(api, champ_admin):
    client = api(champ_admin)
    track = client.post("/catalog/tracks", {"key": "ks_highlands", "name": "Highlands"})
    assert track.status_code == 201
    layout = client.post(
        f"/catalog/tracks/{track.json()['id']}/layouts", {"key": "layout_long", "name": "Long"}
    )
    assert layout.status_code == 201
    assert client.post("/catalog/cars", {"key": "acura", "name": "Acura"}).status_code == 201
    assert client.get("/catalog/tracks").json()[0]["layouts"][0]["name"] == "Long"


def test_driver_cannot_change_the_catalog(api, driver_user):
    response = api(driver_user).post("/catalog/cars", {"key": "acura", "name": "Acura"})
    assert response.status_code == 403


class TestChampionshipScope:
    def test_driver_sees_only_own_championships(
        self, api, driver_user, championship, other_championship
    ):
        names = [c["name"] for c in api(driver_user).get("/championships").json()]
        assert names == ["LMDh"]

    def test_driver_cannot_open_another_championship(self, api, driver_user, other_championship):
        assert api(driver_user).get(f"/championships/{other_championship.id}").status_code == 404

    def test_driver_can_view_but_not_change_a_season(self, api, driver_user, season, layout):
        client = api(driver_user)
        assert client.get(f"/seasons/{season.id}").json()["can_manage"] is False
        response = client.post(
            f"/seasons/{season.id}/rounds",
            {"track_layout_id": layout.id, "scheduled_at": ROUND_DATE},
        )
        assert response.status_code == 403

    def test_championship_admin_cannot_manage_another_championship(
        self, api, champ_admin, other_championship
    ):
        response = api(champ_admin).post(
            f"/championships/{other_championship.id}/seasons",
            {"name": "2026", "planned_round_count": 8},
        )
        assert response.status_code == 404

    def test_championship_admin_cannot_make_leagues_or_link_accounts(
        self, api, champ_admin, make_user
    ):
        client = api(champ_admin)
        assert client.post("/leagues", {"name": "Other"}).status_code == 403
        driver = DriverProfile.objects.create(display_name="X")
        response = client.post(f"/drivers/{driver.id}/link", {"user_id": make_user("x").id})
        assert response.status_code == 403

    def test_championship_admin_gives_a_user_the_driver_role(
        self, api, champ_admin, championship, make_user
    ):
        newcomer = make_user("newcomer")
        response = api(champ_admin).put(
            f"/championships/{championship.id}/members",
            {"user_id": newcomer.id, "role": "driver"},
        )
        assert response.status_code == 200
        assert [c["name"] for c in api(newcomer).get("/championships").json()] == ["LMDh"]

    def test_league_admin_sees_every_championship(
        self, api, league_admin, championship, other_championship
    ):
        names = {c["name"] for c in api(league_admin).get("/championships").json()}
        assert names == {"LMDh", "GT3"}

    @pytest.mark.parametrize("path", ["/championships", "/drivers", "/catalog/tracks"])
    def test_anonymous_user_gets_401(self, api, path, db):
        assert api().get(path).status_code == 401
