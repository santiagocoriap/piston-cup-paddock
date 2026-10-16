"""Incidents: one crash with many events is one incident. Steward reviews."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.collectors.incidents import Collision, group
from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
START = datetime(2026, 10, 11, 19, 30, tzinfo=TZ)


def hit(event_id, seconds, car, other=None, speed=50.0):
    return Collision(
        id=event_id,
        at=START + timedelta(seconds=seconds),
        kind="collision_car" if other else "collision_env",
        car=car,
        other=other,
        speed_kmh=speed,
        x=1.0,
        z=2.0,
        attempt=1,
        lap=1,
    )


def test_both_sides_of_a_contact_and_the_wall_after_are_one_incident():
    events = [
        hit(1, 0.0, "a", "b", 80),
        hit(2, 0.0, "b", "a", 80),  # AC sends the same contact for the other car.
        hit(3, 0.0, "b", "a", 80),  # A repeated packet.
        hit(4, 1.5, "b", speed=120),  # B goes into the wall.
        hit(5, 30.0, "c"),  # Another car, later: another incident.
    ]
    incidents = group(events)
    assert len(incidents) == 2
    assert incidents[0].cars == {"a", "b"}
    assert incidents[0].kind == "car"
    assert incidents[0].max_speed == 120
    assert incidents[1].kind == "env"


def test_a_gap_starts_a_new_incident():
    assert len(group([hit(1, 0, "a"), hit(2, 5, "a")])) == 2


def test_an_event_that_joins_two_incidents_makes_one():
    incidents = group([hit(1, 0, "a"), hit(2, 0.5, "b"), hit(3, 1.0, "a", "b")])
    assert len(incidents) == 1
    assert [e.id for e in incidents[0].events] == [1, 2, 3]


@pytest.fixture
def night(api, champ_admin, championship, season, layout, car):
    for n, guid in ((1, "7656119000000001"), (2, "7656119000000002")):
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"Driver {n}", steam_guid=guid),
            car=car,
            number=n,
        )
    round_ = Round.objects.create(season=season, number=1, track_layout=layout, scheduled_at=START)
    token, _ = create_token(championship, "AC", champ_admin)
    rows = [
        ("session_started", 0, {"type": 3}),
        (
            "collision_car",
            60,
            {
                "guid": "7656119000000001",
                "speed_kmh": 70,
                "x": 10,
                "z": 5,
                "other": {"guid": "7656119000000002"},
            },
        ),
        (
            "collision_car",
            60,
            {
                "guid": "7656119000000002",
                "speed_kmh": 70,
                "x": 10,
                "z": 5,
                "other": {"guid": "7656119000000001"},
            },
        ),
        ("lap_completed", 200, {"guid": "7656119000000001"}),
        ("session_started", 300, {"type": 3}),  # A restart: attempt 2.
        ("collision_env", 400, {"guid": "7656119000000002", "speed_kmh": 150, "x": -3, "z": 8}),
    ]
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="run",
            seq=seq,
            kind=kind,
            occurred_at=START + timedelta(seconds=seconds),
            data=data,
        )
    return round_


def test_round_incidents_with_names_attempts_and_laps(api, champ_admin, night):
    data = api(champ_admin).get(f"/rounds/{night.id}/incidents").json()
    assert data["has_events"] is True and data["gap_seconds"] == 3
    first, second = data["incidents"]
    assert first["cars"] == ["Driver 1", "Driver 2"]
    assert (first["attempt"], first["lap"], len(first["events"])) == (1, 1, 2)
    assert (second["attempt"], second["kind"], second["max_speed"]) == (2, "env", 150)
    assert (
        api(champ_admin).get(f"/rounds/{night.id}/incidents?session=qualifying").json()["incidents"]
        == []
    )


def test_steward_reviews_an_incident(api, make_user, championship, night):
    steward = make_user("steward")
    ChampionshipMember.objects.create(
        championship=championship, user=steward, role=ChampionshipMember.Role.STEWARD
    )
    client = api(steward)
    key = client.get(f"/rounds/{night.id}/incidents").json()["incidents"][0]["key"]
    data = client.put(
        f"/rounds/{night.id}/incidents/{key}/review",
        {"outcome": "racing_incident", "note": "Contacto en la largada"},
    ).json()
    review = data["incidents"][0]["review"]
    assert (review["outcome"], review["reviewed_by"]) == ("racing_incident", "steward")
    assert (
        client.put(f"/rounds/{night.id}/incidents/999999/review", {"outcome": "open"}).status_code
        == 404
    )


def test_driver_sees_incidents_but_cannot_review(api, driver_user, night):
    client = api(driver_user)
    data = client.get(f"/rounds/{night.id}/incidents").json()
    assert data["can_review"] is False and len(data["incidents"]) == 2
    key = data["incidents"][0]["key"]
    response = client.put(f"/rounds/{night.id}/incidents/{key}/review", {"outcome": "open"})
    assert response.status_code == 403


def test_round_without_events_has_no_incidents(api, champ_admin, season, layout):
    round_ = Round.objects.create(season=season, number=2, track_layout=layout, scheduled_at=START)
    data = api(champ_admin).get(f"/rounds/{round_.id}/incidents").json()
    assert (data["has_events"], data["incidents"]) == (False, [])


def test_only_the_last_start_counts_for_the_race(api, champ_admin, night):
    from apps.collectors.incident_api import accepted_race_incidents

    data = api(champ_admin).get(f"/rounds/{night.id}/incidents").json()
    assert data["last_start"] == 2
    incidents, _, _ = accepted_race_incidents(night)
    # The contact of start 1 is from before the restart. Only the wall of start 2 counts.
    assert [i.kind for i in incidents] == ["env"]


def test_a_crash_only_in_the_first_start_does_not_count(champ_admin, night):
    from apps.collectors.incident_api import accepted_race_incidents

    CollectorEvent.objects.filter(kind="collision_env").delete()
    incidents, _, has_events = accepted_race_incidents(night)
    assert has_events and incidents == []
