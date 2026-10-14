"""Phase 4: "Enviar al servidor" makes a race setup for the server collector."""

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Car, Track, TrackLayout
from apps.collectors.models import ServerPush
from apps.collectors.server_setup import sun_angle
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season,
        number=3,
        track_layout=layout,
        scheduled_at=timezone.now(),
        announced_conditions={
            "time_of_day": "15:30",
            "weather": "Despejado",
            "air_temp_c": 24,
            "track_temp_c": 31,
            "grip": "89%",
        },
    )


@pytest.fixture
def entries(season):
    car = Car.objects.create(key="trr_lmdh_acura_arx-06", name="Acura")
    ana = DriverProfile.objects.create(display_name="Ana", steam_guid="76561190000000001")
    bob = DriverProfile.objects.create(display_name="Bob")
    return [
        SeasonEntry.objects.create(season=season, driver=ana, car=car, number=7, team="Rojo"),
        SeasonEntry.objects.create(season=season, driver=bob, car=car, number=8),
    ]


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()["key"]


def collector(key, method, path, body=None):
    client = Client()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {key}"}
    if method == "get":
        return client.get(f"/api{path}", **headers)
    return client.post(f"/api{path}", body or {}, content_type="application/json", **headers)


def test_sun_angle_of_a_clock_time():
    assert (sun_angle("13:00"), sun_angle("15:30"), sun_angle("08:00"), sun_angle("x")) == (
        0,
        40,
        -80,
        None,
    )


def test_the_preview_shows_what_goes_to_the_server(api, champ_admin, round_, entries):
    setup = api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()
    assert setup["track"] == {"key": "ks_highlands", "layout": "layout_long"}
    assert [(e["name"], e["guid"], e["model"]) for e in setup["entries"]] == [
        ("Ana", "76561190000000001", "trr_lmdh_acura_arx-06"),
        ("Bob", "", "trr_lmdh_acura_arx-06"),
    ]
    # 15:30 is a sun angle of 40. The road is 7 °C over the air. "Despejado" is not an AC
    # weather name, so the server keeps its weather.
    assert setup["conditions"] == {
        "sun_angle": 40,
        "air_temp_c": 24,
        "road_offset_c": 7,
        "grip_pct": 89,
    }
    assert set(setup["warnings"]) == {"no_guid:Bob", "weather_kept"}
    assert setup["latest"] is None


def test_the_collector_gets_the_push_and_reports_each_step(api, champ_admin, key, round_, entries):
    first = api(champ_admin).post(f"/rounds/{round_.id}/server-push").json()["latest"]
    second = api(champ_admin).post(f"/rounds/{round_.id}/server-push").json()["latest"]
    assert ServerPush.objects.get(pk=first["id"]).status == "cancelled"  # The newer one wins.

    command = collector(key, "get", "/collector/commands").json()
    assert command["id"] == second["id"]
    code = command["content"]["script"]["race_code"]
    assert (
        code == round_.season.championship.script_codes.filter(replaced_at__isnull=True).get().code
    )
    assert command["content"]["entries"][0]["guid"] == "76561190000000001"

    waiting = collector(
        key,
        "post",
        f"/collector/commands/{second['id']}",
        {"status": "waiting", "error": "server_running"},
    )
    assert waiting.json()["status"] == "waiting"
    assert collector(key, "get", "/collector/commands").json()["id"] == second["id"]  # Still to do.

    done = collector(key, "post", f"/collector/commands/{second['id']}", {"status": "done"})
    assert (done.json()["status"], done.json()["collector"]) == ("done", "AC")
    assert collector(key, "get", "/collector/commands").json() == {"id": None, "content": None}
    latest = api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()["latest"]
    assert latest["status"] == "done"


def test_only_an_admin_sends_to_the_server(api, driver_user, round_, entries):
    assert api(driver_user).post(f"/rounds/{round_.id}/server-push").status_code in (403, 404)


def test_another_championship_does_not_see_the_push(
    api, champ_admin, key, round_, entries, other_championship, league_admin
):
    api(champ_admin).post(f"/rounds/{round_.id}/server-push")
    other = api(league_admin).post(
        f"/championships/{other_championship.id}/collectors", {"name": "B"}
    )
    other_key = other.json()["key"]
    assert collector(other_key, "get", "/collector/commands").json() == {
        "id": None,
        "content": None,
    }


def test_a_name_with_a_line_break_is_cleaned(api, champ_admin, round_, entries):
    driver = entries[0].driver
    driver.display_name = "Ana\nADMIN_PASSWORD=x"
    driver.save()
    setup = api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()
    assert setup["entries"][0]["name"] == "Ana ADMIN_PASSWORD=x"


def test_the_admin_sets_the_open_slots(api, champ_admin, championship, key, round_, entries):
    assert api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()["open_slots"] == 10
    response = api(champ_admin).client.patch(
        f"/api/championships/{championship.id}/settings",
        {"open_slots": 4},
        content_type="application/json",
    )
    assert response.json()["open_slots"] == 4
    assert api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()["open_slots"] == 4

    # One push with another number. The setting stays.
    api(champ_admin).post(f"/rounds/{round_.id}/server-push", {"open_slots": 12})
    assert collector(key, "get", "/collector/commands").json()["content"]["open_slots"] == 12
    assert api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()["open_slots"] == 4
    too_many = api(champ_admin).client.patch(
        f"/api/championships/{championship.id}/settings",
        {"open_slots": 99},
        content_type="application/json",
    )
    assert too_many.status_code == 422


def test_the_admin_picks_another_preset(api, champ_admin, key, round_, entries):
    sent = {
        "presets": [
            {"folder": "SERVER_01", "name": "EIST Server - Piston Cup (SERVER_01)"},
            {"folder": "Rain Piston", "name": "EIST Server - Piston Cup (Rain Piston)"},
            {"folder": "../evil", "name": "x"},
        ],
        "current": "SERVER_01",
    }
    assert collector(key, "post", "/collector/presets", sent).json() == {"presets": 2}
    setup = api(champ_admin).get(f"/rounds/{round_.id}/server-setup").json()
    assert [p["folder"] for p in setup["presets"]] == ["SERVER_01", "Rain Piston"]
    assert setup["preset"] == "SERVER_01"

    api(champ_admin).post(f"/rounds/{round_.id}/server-push", {"preset": "Rain Piston"})
    assert collector(key, "get", "/collector/commands").json()["content"]["preset"] == "Rain Piston"
    wrong = api(champ_admin).client.post(
        f"/api/rounds/{round_.id}/server-push",
        {"preset": "../evil"},
        content_type="application/json",
    )
    assert wrong.status_code == 422
