"""Full classification: times, gaps, laps down, and incidents. Contact laps in lap tables."""

from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round
from apps.imports.lap_analysis import LapRow, analyze

D1, D3 = "76561190000000001", "76561190000000003"


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def add_contact(admin, round_, lap_events_before=2):
    token, _ = create_token(round_.season.championship, "AC", admin)
    rows = [("session_started", 0, {"type": 3})]
    rows += [("lap_completed", 10 + n, {"guid": D1}) for n in range(lap_events_before)]
    rows += [
        ("collision_car", 300, {"guid": D1, "speed_kmh": 60, "other": {"guid": D3}}),
        ("collision_car", 300, {"guid": D3, "speed_kmh": 60, "other": {"guid": D1}}),
    ]
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="run",
            seq=seq,
            kind=kind,
            occurred_at=round_.scheduled_at + timedelta(seconds=seconds),
            data=data,
        )


def test_classification_has_gaps_laps_down_and_no_incident_data(api, night):
    admin, round_ = night
    lines = api(admin).get(f"/rounds/{round_.id}").json()["result"]
    winner, second, third = lines[0], lines[1], lines[2]
    assert (winner["laps"], winner["gap_ms"], winner["laps_down"]) == (10, None, None)
    assert second["gap_ms"] == second["total_ms"] - winner["total_ms"] > 0
    assert third["laps_down"] == 1  # Driver 06 finished 9 laps.
    assert {line["incidents"] for line in lines} == {None}  # No collector events.


def test_classification_counts_incidents(api, night):
    admin, round_ = night
    add_contact(admin, round_)
    lines = api(admin).get(f"/rounds/{round_.id}").json()["result"]
    counts = {line["driver_name"]: line["incidents"] for line in lines}
    assert counts["Driver 01"] == 1 and counts["Driver 03"] == 1 and counts["Driver 06"] == 0


def test_contact_lap_leaves_the_clean_average(api, night):
    admin, round_ = night
    add_contact(admin, round_, lap_events_before=2)  # The contact is on lap 3 of Driver 01.
    data = api(admin).get(f"/rounds/{round_.id}/laps").json()
    assert "contact" in data["clean_rules"]
    driver = next(d for d in data["drivers"] if d["driver_name"] == "Driver 01")
    assert [lap["lap_number"] for lap in driver["laps"] if lap["contact"]] == [3]
    assert driver["clean_average"]["excluded"]["contact"] == 1


def test_no_contact_rule_without_collector_data():
    rows = {"a": [LapRow(2, 100, [], contact=True), LapRow(3, 102, [])]}
    (without,) = analyze(rows, race=True)
    (with_data,) = analyze(rows, race=True, contacts=True)
    assert without.clean_average.laps == 2
    assert with_data.clean_average.laps == 1
