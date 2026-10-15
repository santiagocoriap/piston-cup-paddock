"""Lap comparison: default laps, sector differences, and the delta along the track."""

from datetime import datetime

import pytest
from django.core.management import call_command

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.imports.delta import delta
from apps.imports.models import ImportedLap

from .telemetry_laps import save_lap


def lap(seconds_per_tenth):
    """A lap with ten parts. Each part takes the given seconds."""
    pos, t_ms, total = [0.995], [0], 0  # The first sample still shows the last lap.
    for index, seconds in enumerate(seconds_per_tenth):
        pos.append(round((index + 1) / 10, 3))
        total += seconds * 1000
        t_ms.append(total)
    return {"pos": pos, "t_ms": t_ms, "speed_kmh": [200] * len(pos)}


def test_delta_aligns_by_position_and_shows_the_sign():
    a = lap([10] * 10)
    b = lap([10] * 5 + [11] * 5)  # B loses one second in each of the last five parts.
    result = delta(a, b)
    by_pos = dict(zip(result["pos"], result["delta_ms"], strict=True))
    assert by_pos[0.5] == 0
    assert by_pos[1.0] == 5000  # Positive: B is behind.
    assert by_pos[0.75] == 2500
    assert result["coverage"] == pytest.approx(0.9)  # The first sample from the last lap is out.


def test_delta_needs_positions():
    assert delta({"t_ms": [0, 1]}, lap([10] * 10)) is None


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def test_default_is_the_viewers_best_against_the_session_best(api, night, make_user):
    admin, round_ = night
    data = api(admin).get(f"/rounds/{round_.id}/compare").json()
    # The admin has no lap: the two best laps of two drivers. B is the session best.
    assert data["b"]["driver_name"] == "Driver 01"
    assert data["b"]["lap_time_ms"] == 189296
    assert data["a"]["driver_name"] != "Driver 01"
    assert len(data["sector_diff_ms"]) == 3
    assert data["sector_diff_ms"][0] == data["b"]["sectors_ms"][0] - data["a"]["sectors_ms"][0]
    assert "no_telemetry" in data["gaps"] and "no_map" in data["gaps"]
    assert data["a"]["car"] and data["a"]["tyre"]

    entry = SeasonEntry.objects.get(driver__display_name="Driver 03")
    user = make_user("d3")
    entry.driver.user = user
    entry.driver.save()
    ChampionshipMember.objects.create(
        championship=round_.season.championship, user=user, role=ChampionshipMember.Role.DRIVER
    )
    mine = api(user).get(f"/rounds/{round_.id}/compare").json()
    assert mine["a"]["driver_name"] == "Driver 03"
    assert mine["b"]["driver_name"] == "Driver 01"


def test_chosen_laps_and_telemetry_delta(api, night):
    admin, round_ = night
    best = ImportedLap.objects.filter(lap_time_ms=189296).select_related("entry__driver").get()
    other = (
        ImportedLap.objects.filter(
            result_import=best.result_import, cuts=0, invalid_reason="", entry__isnull=False
        )
        .exclude(entry=best.entry)
        .order_by("lap_time_ms")
        .select_related("entry__driver")
        .first()
    )
    for item, seconds in ((best, 10), (other, 11)):
        save_lap(
            item.entry.driver,
            round_,
            lap([seconds] * 10),
            car="car",
            session_type="",
            lap_number=item.lap_number,
            lap_time_ms=item.lap_time_ms,
            recorded_at=datetime.fromisoformat("2026-10-11T22:40:00+00:00"),
        )

    data = api(admin).get(f"/rounds/{round_.id}/compare?a={best.id}&b={other.id}").json()
    assert (data["a"]["telemetry"], data["b"]["telemetry"]) == ("laps", "laps")
    assert data["delta"]["delta_ms"][-1] == 10000
    assert data["speed_a"]["speed_kmh"][0] == 200
    assert "no_telemetry" not in data["gaps"]


def test_lap_of_another_session_is_refused(api, night):
    admin, round_ = night
    qualifying = ImportedLap.objects.filter(result_import__session__kind="qualifying").first()
    race = ImportedLap.objects.filter(result_import__session__kind="race").first()
    response = api(admin).get(f"/rounds/{round_.id}/compare?a={qualifying.id}&b={race.id}")
    assert response.json()["detail"] == "lap_not_in_session"
