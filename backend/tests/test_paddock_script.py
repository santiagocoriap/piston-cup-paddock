"""Phase 2: laps of the Paddock script count only when the server says the driver was there."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile, DriverSteamId
from apps.telemetry.models import ScriptCode, TelemetryLap
from apps.telemetry.samples import read_samples
from apps.telemetry.script import CODE_GRACE
from apps.telemetry.services import channels_for

GUID = "76561190000000001"
CAR = "TRR_LMDh_acura_arx-06"


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def round_(season):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    layout = TrackLayout.objects.create(track=track, key="layout_long", name="Long")
    return Round.objects.create(
        season=season, number=3, track_layout=layout, scheduled_at=timezone.now()
    )


@pytest.fixture
def driver(season):
    profile = DriverProfile.objects.create(display_name="Ana", steam_guid=GUID)
    car = Car.objects.create(key=CAR.lower(), name="Acura")
    SeasonEntry.objects.create(season=season, driver=profile, car=car, number=7)
    return profile


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()["key"]


@pytest.fixture
def code(api, champ_admin, championship):
    return api(champ_admin).get(f"/championships/{championship.id}/script").json()["race_code"]


def at(minutes: float) -> str:
    return (timezone.now() + timedelta(minutes=minutes)).isoformat()


def events(key, *items, run_id="run-1"):
    batch = {
        "run_id": run_id,
        "events": [
            {"seq": n, "kind": kind, "at": when, "data": data}
            for n, (kind, when, data) in enumerate(items)
        ],
    }
    return Client().post(
        "/api/collector/events",
        batch,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )


def race_started(minutes=-30):
    return (
        "session_started",
        at(minutes),
        {"type": 3, "track": "ks_highlands", "layout": "layout_long"},
    )


def connected(minutes=-31, guid=GUID, car=CAR):
    return ("connected", at(minutes), {"car_id": 0, "guid": guid, "name": "Ana", "car_model": car})


def server_lap(minutes=0, guid=GUID, lap_ms=113_689, cuts=0):
    """The server records the same lap: the witness for the lap of the script."""
    data = {"car_id": 0, "guid": guid, "lap_ms": lap_ms, "cuts": cuts}
    return ("lap_completed", at(minutes), data)


def lap(
    code,
    *,
    number=2,
    car=CAR,
    steam_id=GUID,
    ended_at=1_800_000_000,
    sent_at=None,
    lap_time_ms=113_689,
    samples=None,
):
    payload = {
        "steam_id": steam_id,
        "track": "ks_highlands",
        "layout": "layout_long",
        "car": car,
        "lap_number": number,
        "lap_time_ms": lap_time_ms,
        "valid": True,
        "cuts": 0,
        "ended_at": ended_at,
        "sent_at": sent_at if sent_at is not None else ended_at + 5,
        "samples": samples
        or [[t * lap_time_ms // 99, t / 100, 100.5, 1, 0, -2.5, 4, 7000] for t in range(100)],
    }
    return Client().post(
        "/api/script/laps", payload, content_type="application/json", HTTP_X_PADDOCK_CODE=code
    )


def test_a_lap_on_the_league_server_counts(key, code, round_, driver):
    events(key, connected(), race_started(), server_lap())
    response = lap(code)
    assert response.json() == {"state": "league", "lap_number": 1, "cuts": 0, "issues": []}

    saved = TelemetryLap.objects.get()
    assert (saved.source, saved.match, saved.round, saved.session_type) == (
        "script",
        "league",
        round_,
        "race",
    )
    assert saved.attempt_number == 1
    assert saved.sample_hz == 20


def test_a_wrong_pc_clock_still_matches(key, code, round_, driver):
    events(key, connected(), race_started(), server_lap(-0.5))
    # The PC clock says 1970. The app uses only the age of the lap: 30 seconds.
    response = lap(code, ended_at=1_000, sent_at=1_030)
    assert response.json()["state"] == "league"
    saved = TelemetryLap.objects.get()
    assert abs((timezone.now() - saved.recorded_at).total_seconds() - 30) < 5


def test_a_lap_before_the_server_data_waits_and_then_counts(key, code, round_, driver):
    assert lap(code).json()["state"] == "pending"
    assert TelemetryLap.objects.get().round is None  # Nobody sees it yet.

    events(key, connected(), race_started(), server_lap(), ("lap_completed", at(3), {"car_id": 0}))

    saved = TelemetryLap.objects.get()
    assert (saved.match, saved.round) == ("league", round_)


def flagged() -> TelemetryLap:
    return TelemetryLap.objects.get(match="flagged")


def test_a_driver_who_was_not_connected_is_kept_for_review(key, code, round_, driver):
    other = "76561190000000099"
    events(key, connected(guid=other), race_started(), ("lap_completed", at(3), {"car_id": 0}))
    assert lap(code).json() == {
        "state": "rejected",
        "lap_number": None,
        "cuts": None,
        "issues": ["not_connected"],
    }
    kept = flagged()
    assert (kept.driver, kept.round, kept.issues) == (driver, None, ["not_connected"])


def test_another_car_is_kept_for_review(key, code, round_, driver):
    events(key, connected(), race_started(), ("lap_completed", at(3), {"car_id": 0}))
    assert lap(code, car="ks_mazda_mx5_cup").json()["issues"] == ["other_car"]
    assert flagged().issues == ["other_car"]


def test_a_lap_after_the_session_goes_nowhere(key, code, round_, driver):
    events(
        key,
        connected(-60),
        race_started(-50),
        ("session_ended", at(-20), {"result_file": "x.json"}),
        ("lap_completed", at(3), {"car_id": 0}),
    )
    assert lap(code).json()["issues"] == ["no_session"]


def test_restarts_give_the_race_start_number(key, code, round_, driver):
    events(
        key,
        connected(-60),
        race_started(-50),
        race_started(-40),
        race_started(-30),
        server_lap(),
    )
    lap(code)
    assert TelemetryLap.objects.get().attempt_number == 3


def test_the_race_code_and_the_driver_are_checked(
    api, champ_admin, championship, key, code, round_, driver
):
    events(
        key,
        connected(),
        race_started(),
        server_lap(),
        server_lap(lap_ms=114_000),
        server_lap(lap_ms=115_000),
    )
    assert lap("not-a-code").status_code == 401
    unknown = lap(code_of(championship), steam_id="76561190000000098").json()
    assert unknown["issues"] == ["unknown_driver"]
    assert flagged().steam_guid == "76561190000000098"

    old = code_of(championship)
    new = api(champ_admin).post(f"/championships/{championship.id}/script/code").json()["race_code"]
    assert new != old
    assert (
        lap(old, number=3, lap_time_ms=114_000).json()["state"] == "league"
    )  # A race in progress keeps working.
    ScriptCode.objects.filter(code=old).update(replaced_at=timezone.now() - CODE_GRACE * 2)
    assert lap(old, number=4).status_code == 401
    assert lap(new, number=5, lap_time_ms=115_000).json()["state"] == "league"


def code_of(championship) -> str:
    return championship.script_codes.order_by("created_at").first().code


def test_a_driver_of_another_championship_is_refused(code, round_, other_championship):
    stranger = DriverProfile.objects.create(display_name="Bob", steam_guid="76561190000000077")
    assert stranger.id
    response = lap(code, steam_id="76561190000000077")
    assert response.json()["issues"] == ["not_in_championship"]
    assert flagged().driver == stranger


def test_the_line_in_ac_shows_the_session(key, code, round_, driver):
    events(key, connected(), race_started())
    now = Client().get("/api/script/now", HTTP_X_PADDOCK_CODE=code).json()
    assert now == {"session_type": "race", "round_number": 3, "label": "Fecha 3 · Carrera"}


def test_the_script_has_the_app_address(client):
    response = client.get("/api/script/paddock.lua")
    assert response.status_code == 200
    body = response.content.decode()
    assert "__PADDOCK_URL__" not in body
    assert "local PADDOCK_URL = 'http://testserver'" in body


def test_only_an_admin_sees_the_server_setup(api, champ_admin, driver_user, championship):
    setup = api(champ_admin).get(f"/championships/{championship.id}/script").json()
    assert setup["csp_section"].startswith(
        "[SCRIPT_1]\nSCRIPT = 'http://testserver/api/script/paddock.lua'"
    )
    assert f"raceCode = '{setup['race_code']}'" in setup["csp_section"]
    assert api(driver_user).get(f"/championships/{championship.id}/script").status_code in (
        403,
        404,
    )


def test_another_driver_cannot_send_a_lap_in_my_name(key, code, round_, driver):
    """Every driver on the server gets the race code. A lap with my Steam ID but with no lap of
    mine on the server goes nowhere."""
    events(
        key,
        connected(),
        race_started(),
        server_lap(lap_ms=120_000),
        ("lap_completed", at(3), {"car_id": 1}),
    )
    # 113.689 s, but the server saw 120.000 s.
    assert lap(code).json()["issues"] == ["no_server_lap"]


def test_a_server_lap_counts_one_time(key, code, round_, driver):
    events(key, connected(), race_started(), server_lap(), ("lap_completed", at(3), {"car_id": 1}))
    assert lap(code).json()["state"] == "league"
    # A second upload for the same server lap, with other samples.
    assert lap(code, number=9, ended_at=1_800_000_001).json()["issues"] == ["duplicate"]
    assert TelemetryLap.objects.filter(match="league").count() == 1


def test_an_admin_reviews_the_laps_with_issues(
    api, champ_admin, driver_user, championship, key, code, round_, driver
):
    """A driver raced with a second Steam account. The app keeps the laps. The admin adds the
    Steam ID, and the laps count."""
    alt = "76561190000000055"
    events(key, connected(guid=alt), race_started(), server_lap(guid=alt))
    assert lap(code, steam_id=alt).json()["issues"] == ["unknown_driver"]
    admin = api(champ_admin)
    rows = admin.get(f"/championships/{championship.id}/telemetry/flagged").json()
    assert [(r["steam_guid"], r["issues"], r["round_id"]) for r in rows] == [
        (alt, ["unknown_driver"], round_.id)
    ]
    assert api(driver_user).get(
        f"/championships/{championship.id}/telemetry/flagged"
    ).status_code in (403, 404)
    lap_id = rows[0]["id"]
    assert admin.post(f"/telemetry-laps/{lap_id}/recheck").json()["issues"] == ["unknown_driver"]
    DriverSteamId.objects.create(driver=driver, guid=alt)
    assert admin.post(f"/telemetry-laps/{lap_id}/recheck").json() == {
        "state": "league",
        "issues": [],
    }
    saved = TelemetryLap.objects.get()
    assert (saved.driver, saved.round, saved.match) == (driver, round_, "league")


def test_a_new_steam_id_rechecks_the_kept_laps(api, league_admin, key, code, round_, driver):
    alt = "76561190000000055"
    events(key, connected(guid=alt), race_started(), server_lap(guid=alt))
    lap(code, steam_id=alt)
    api(league_admin).post(f"/drivers/{driver.id}/steam-ids", {"guid": alt})
    assert TelemetryLap.objects.get().match == "league"


def test_an_admin_counts_or_deletes_a_lap_with_issues(
    api, champ_admin, championship, key, code, round_, driver
):
    # The collector lost the server lap: the lap has no witness.
    events(key, connected(), race_started(), ("lap_completed", at(3), {"car_id": 1}))
    lap(code)
    lap(code, number=3, ended_at=1_800_000_100)
    admin = api(champ_admin)
    first, second = TelemetryLap.objects.order_by("lap_number")
    accepted = admin.post(
        f"/telemetry-laps/{first.id}/accept", {"round_id": round_.id, "session_type": "race"}
    )
    assert accepted.json()["state"] == "league"
    first.refresh_from_db()
    assert (first.round, first.session_type, first.issues) == (round_, "race", ["no_server_lap"])
    assert admin.delete(f"/telemetry-laps/{second.id}").status_code == 204
    assert TelemetryLap.objects.count() == 1
    # Only a flagged lap is in the review.
    assert admin.delete(f"/telemetry-laps/{first.id}").status_code == 404


def test_bad_samples_are_kept_as_they_came(key, code, round_, driver):
    payload = {
        "steam_id": GUID,
        "track": "ks_highlands",
        "layout": "layout_long",
        "car": CAR,
        "lap_number": 2,
        "lap_time_ms": 113_689,
        "valid": True,
        "cuts": 0,
        "ended_at": 1_800_000_000,
        "sent_at": 1_800_000_005,
        "samples": [[1, 2]],
    }
    response = Client().post(
        "/api/script/laps", payload, content_type="application/json", HTTP_X_PADDOCK_CODE=code
    )
    assert response.json()["issues"] == ["bad_samples"]
    with flagged().samples.open("rb") as handle:
        assert read_samples(handle) == {"raw": [[1, 2]]}


def test_the_server_gives_the_lap_number_and_the_cuts(key, code, round_, driver):
    """The live test of October 14: CSP said lap 0 two times, and "valid" for laps with cuts.
    The server is right, so the app uses its numbers. A lap with cuts still counts."""
    events(
        key,
        connected(-10),
        race_started(-9),
        server_lap(-4, lap_ms=143_902, cuts=2),
        server_lap(-2, lap_ms=113_860, cuts=2),
        server_lap(0, lap_ms=105_337, cuts=0),
        ("lap_completed", at(3), {"car_id": 1}),
    )
    first = lap(code, number=0, lap_time_ms=143_902, ended_at=1_000, sent_at=1_240)
    second = lap(code, number=0, lap_time_ms=113_860, ended_at=2_000, sent_at=2_120)
    third = lap(code, number=1, lap_time_ms=105_337, ended_at=3_000, sent_at=3_000)

    assert first.json() == {"state": "league", "lap_number": 1, "cuts": 2, "issues": []}
    assert second.json() == {"state": "league", "lap_number": 2, "cuts": 2, "issues": []}
    assert third.json() == {"state": "league", "lap_number": 3, "cuts": 0, "issues": []}
    saved = list(
        TelemetryLap.objects.order_by("lap_number").values_list("lap_number", "valid", "cuts")
    )
    assert saved == [(1, False, 2), (2, False, 2), (3, True, 0)]


def test_a_long_lap_with_a_crash_and_a_pit_stop_counts(key, code, round_, driver):
    """The lap timer runs until the car crosses the line: 2 minutes, a crash, the pits, and a
    full lap of 3 minutes are one lap of 5 minutes, with 6,000 samples."""
    events(key, connected(-10), race_started(-9), server_lap(0, lap_ms=300_000, cuts=0))
    payload_samples = [[t * 50, (t % 3600) / 3600, 80.0, 1, 0, 0, 3, 6000] for t in range(6000)]
    response = Client().post(
        "/api/script/laps",
        {
            "steam_id": GUID,
            "track": "ks_highlands",
            "layout": "layout_long",
            "car": CAR,
            "lap_number": 1,
            "lap_time_ms": 300_000,
            "valid": True,
            "cuts": 0,
            "ended_at": 1_000,
            "sent_at": 1_002,
            "samples": payload_samples,
        },
        content_type="application/json",
        HTTP_X_PADDOCK_CODE=code,
    )
    assert response.json()["state"] == "league"
    assert TelemetryLap.objects.get().lap_time_ms == 300_000


def test_public_url_goes_into_the_script_and_the_server_setup(
    client, api, champ_admin, championship, settings
):
    # The game of every driver loads the script, so the address must be public, not the
    # address that the admin has in the browser.
    settings.PUBLIC_URL = "https://paddock.example.com"
    body = client.get("/api/script/paddock.lua").content.decode()
    assert "local PADDOCK_URL = 'https://paddock.example.com'" in body
    setup = api(champ_admin).get(f"/championships/{championship.id}/script").json()
    assert setup["script_url"] == "https://paddock.example.com/api/script/paddock.lua"


def test_the_laps_that_do_not_count_have_a_storage_limit(key, code, round_, driver, monkeypatch):
    monkeypatch.setattr("apps.telemetry.script.MAX_REVIEW_BYTES", 1)
    # No server data: the first lap of a real driver waits, then the limit removes it.
    assert lap(code).json()["detail"] == "too_many_flagged"
    assert not TelemetryLap.objects.exists()
    # A lap that counts has no limit.
    events(key, connected(), race_started(), server_lap())
    assert lap(code).json()["state"] == "league"
    # A made-up Steam ID has no room once the review is full.
    TelemetryLap.objects.update(match="flagged")
    assert lap(code, steam_id="76561190000000098").json()["detail"] == "too_many_flagged"
    assert TelemetryLap.objects.count() == 1


def test_a_lap_with_samples_of_a_small_part_of_the_lap_is_kept_for_review(
    api, champ_admin, key, code, round_, driver
):
    """The script once sent only the samples after the line. The chart then shows a short line."""
    events(key, connected(), race_started(), server_lap())
    few = [[t * 50, t / 2000, 100.5, 1, 0, -2.5, 4, 7000] for t in range(5)]
    assert lap(code, samples=few).json()["issues"] == ["partial_samples"]
    kept = flagged()
    admin = api(champ_admin)
    assert admin.post(f"/telemetry-laps/{kept.id}/recheck").json()["issues"] == ["partial_samples"]
    accepted = admin.post(
        f"/telemetry-laps/{kept.id}/accept", {"round_id": round_.id, "session_type": "race"}
    )
    assert accepted.status_code == 422


def _vehicle_row(t_ms, place, fuel, in_pit=0):
    wheels = [80.0] * 16 + [27.0] * 4 + [0.1] * 4 + [0.05] * 4 + [0.02] * 4
    return [t_ms, place, in_pit, fuel, *wheels]


def test_the_new_channels_and_the_lap_numbers_are_stored(key, code, round_, driver):
    events(key, connected(), race_started(), server_lap())
    payload = {
        "steam_id": GUID,
        "track": "ks_highlands",
        "layout": "layout_long",
        "car": CAR,
        "lap_number": 2,
        "lap_time_ms": 113_689,
        "valid": True,
        "cuts": 0,
        "ended_at": 1_800_000_000,
        "sent_at": 1_800_000_005,
        "samples": [
            [t * 1148, t / 100, 100.5, 1, 0, -2.5, 4, 7000, t, t * 2, 0.5, -1.0] for t in range(100)
        ],
        "vehicle": [
            _vehicle_row(0, 0.0, 40.0),
            _vehicle_row(50_000, 0.5, 39.0, in_pit=1),
            _vehicle_row(60_000, 0.6, 38.5, in_pit=1),
            _vehicle_row(113_000, 0.99, 37.5),
        ],
    }
    response = Client().post(
        "/api/script/laps", payload, content_type="application/json", HTTP_X_PADDOCK_CODE=code
    )
    assert response.json()["state"] == "league"
    saved = TelemetryLap.objects.get()
    assert saved.summary == {
        "fuel_start": 40.0,
        "fuel_end": 37.5,
        "fuel_used": 2.5,
        "pit_ms": 10_000,
        "wear": 0.1,
    }
    channels = channels_for(saved, "full")
    assert channels["g_lat"][0] == 0.5
    assert channels["v_temp_core_fl"][0] == 80
    assert channels["v_pressure_rr"][0] == 27
    assert "v_fuel" not in channels_for(saved, "laps")
    assert saved.samples.open("rb").read(2) == b"\x1f\x8b"  # The file has compression.


def test_a_bad_vehicle_block_does_not_stop_the_lap(key, code, round_, driver):
    events(key, connected(), race_started(), server_lap())
    payload = {
        "steam_id": GUID,
        "track": "ks_highlands",
        "layout": "layout_long",
        "car": CAR,
        "lap_number": 2,
        "lap_time_ms": 113_689,
        "valid": True,
        "cuts": 0,
        "ended_at": 1_800_000_000,
        "sent_at": 1_800_000_005,
        "samples": [[t * 1148, t / 100, 100.5, 1, 0, -2.5, 4, 7000] for t in range(100)],
        "vehicle": [[1, 2]],
    }
    response = Client().post(
        "/api/script/laps", payload, content_type="application/json", HTTP_X_PADDOCK_CODE=code
    )
    assert response.json()["state"] == "league"
    assert TelemetryLap.objects.get().summary == {}
