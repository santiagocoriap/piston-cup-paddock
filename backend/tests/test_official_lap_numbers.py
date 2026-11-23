"""The telemetry lap number comes from the result file, not from the count of server laps."""

import pytest
from django.core.management import call_command

from apps.competition.models import Round, Session
from apps.imports.models import ImportedLap, ResultImport
from apps.telemetry.models import TelemetryLap


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    applied = ResultImport.objects.filter(
        round=round_, session__kind=Session.Kind.RACE, status=ResultImport.State.APPLIED
    ).latest("applied_at")
    lap = ImportedLap.objects.filter(result_import=applied).order_by("lap_number")[4]
    entry = round_.season.entries.get(driver__steam_guid=lap.guid)
    return admin, round_, lap, entry


def script_lap(round_, entry, number, ms, attempt):
    return TelemetryLap.objects.create(
        championship=round_.season.championship,
        driver=entry.driver,
        steam_guid=entry.driver.steam_guid,
        round=round_,
        session_type="race",
        attempt_number=attempt,
        track="ks_highlands",
        car="car",
        lap_number=number,
        lap_time_ms=ms,
        valid=True,
        match=TelemetryLap.Match.LEAGUE,
        recorded_at=round_.scheduled_at,
        sample_hz=20,
        sha256=f"{attempt}-{number}-{ms}",
    )


def test_the_result_file_gives_the_lap_number(api, night):
    admin, round_, lap, entry = night
    shifted = script_lap(round_, entry, lap.lap_number - 1, lap.lap_time_ms, attempt=2)
    earlier = script_lap(round_, entry, 1, lap.lap_time_ms, attempt=1)  # A start before.
    unknown = script_lap(round_, entry, 7, 99_999, attempt=2)  # Not in the file.
    rows = {r["id"]: r for r in api(admin).get(f"/rounds/{round_.id}/telemetry").json()}
    assert rows[shifted.id]["lap_number"] == lap.lap_number
    assert rows[shifted.id]["valid"] == (lap.cuts == 0)
    assert rows[earlier.id]["lap_number"] == 1
    assert rows[unknown.id]["lap_number"] == 7


def test_only_the_laps_of_the_last_start_count(night):
    from apps.telemetry.services import final_laps

    _, round_, lap, entry = night
    shifted = script_lap(round_, entry, lap.lap_number - 1, lap.lap_time_ms, attempt=2)
    script_lap(round_, entry, 1, lap.lap_time_ms, attempt=1)  # A start before: it does not count.
    kept = final_laps(round_, "race")
    assert [k.id for k in kept] == [shifted.id]
    assert kept[0].lap_number == lap.lap_number
