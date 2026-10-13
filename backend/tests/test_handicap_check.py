"""Handicap check: the race file against the assigned ballast and restrictor.

The sample race file has the real values of that night: Driver 01 8 kg, Driver 03 15 kg and
2 %, Driver 05 10 kg and 2 %. The demo season assigns 0 to everybody in round 1.
"""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.competition.models import Round
from apps.handicaps.models import UsedHandicap

from .test_penalty_logs import NIGHT


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def checks_of(client, round_):
    return {
        c["driver_name"]: (c["assigned_kg"], c["assigned_pct"], c["observed_kg"], c["observed_pct"])
        for c in client.get(f"/rounds/{round_.id}").json()["handicap_checks"]
    }


def test_round_shows_drivers_with_other_values(api, night):
    admin, round_ = night
    client = api(admin)
    assert checks_of(client, round_) == {
        "Driver 01": (0, 0, 8, 0),
        "Driver 03": (0, 0, 15, 2),
        "Driver 05": (0, 0, 10, 2),
    }
    used = UsedHandicap.objects.get(round=round_, entry__driver__display_name="Driver 01")
    used.ballast_kg = 8
    used.save()
    assert "Driver 01" not in checks_of(client, round_)  # Same values: no warning.


def test_preview_warns_before_the_import(api, night):
    admin, round_ = night
    client = api(admin)
    # The winner of round 1 carries 10 kg into round 2. The same file shows 8 kg.
    next_round = Round.objects.create(
        season=round_.season,
        number=2,
        track_layout=round_.track_layout,
        scheduled_at=round_.scheduled_at + timedelta(days=7),
    )
    content = (NIGHT / "2026_10_11_20_7_RACE.json").read_bytes()
    response = client.client.post(
        f"/api/rounds/{next_round.id}/imports",
        {"file": SimpleUploadedFile("2026_10_11_20_7_RACE.json", content)},
    )
    drivers = {d["driver_name"]: d for d in response.json()["preview"]["drivers"]}
    winner = drivers["Driver 01"]
    assert "handicap_differs" in winner["warnings"]
    assert (winner["assigned_ballast_kg"], winner["ballast_kg"]) == (10, 8)
    assert "handicap_differs" not in drivers["Driver 06"]["warnings"]  # 0 and 0.
