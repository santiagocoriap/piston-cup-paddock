"""The app creates the restarts from the race starts of the collector, with a responsible driver:
the driver of a jump start penalty, or else the driver of the first collision."""

from datetime import timedelta

import pytest

from apps.audit.models import AuditEntry
from apps.collectors.models import CollectorEvent
from apps.collectors.services import create_token
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.imports.penalty_services import upload_log
from apps.restarts.models import Restart

GUIDS = ["76561190000000001", "76561190000000002", "76561190000000003"]


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def grid(season, car):
    return [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}", steam_guid=guid),
            car=car,
            number=n,
        )
        for n, guid in enumerate(GUIDS, start=1)
    ]


@pytest.fixture
def round_(season, layout, grid):
    created = Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-18T00:00Z"
    )
    created.refresh_from_db()
    return created


def collector(round_, user, rows):
    token, _ = create_token(round_.season.championship, "AC", user)
    for seq, (kind, seconds, data) in enumerate(rows):
        CollectorEvent.objects.create(
            token=token,
            run_id="r",
            seq=seq,
            kind=kind,
            occurred_at=round_.scheduled_at + timedelta(seconds=seconds),
            data=data,
        )


def starts_at(*seconds):
    return [("session_started", s, {"type": 3}) for s in seconds]


def race_log(minute: int, jumpers=()) -> bytes:
    stamp = f"2026-10-17 21:{minute:02d}:00.000000"
    lines = [
        f"{stamp}: ----------------------------------------------------",
        f"{stamp}: Track: ks_highlands / layout_long",
        f"{stamp}: Name: Race",
        f"{stamp}: Type: 3",
        f"{stamp}: ----------------------------------------------------",
    ]
    for car_id, guid in enumerate(jumpers):
        lines.append(
            f"{stamp}: New penalty - Car ID: {car_id} - Name: D - GUID: {guid} - Penalty: "
            "Drive Through - Cause: jump - Other: ['15'] - Lap: 1 - Laps left: 2 - ID: 1 - True"
        )
    lines.append(f"2026-10-17 21:{minute:02d}:50.000000: End session - new info from AC")
    return ("\n".join(lines) + "\n").encode()


def test_a_first_collision_and_a_jump_start_give_the_responsible_drivers(
    api, champ_admin, round_, grid
):
    d1, d2, d3 = grid
    collector(
        round_,
        champ_admin,
        [
            *starts_at(0),
            ("collision_env", 20, {"guid": GUIDS[1], "speed_kmh": 80}),  # D2 crashes first.
            ("collision_car", 22, {"guid": GUIDS[0], "speed_kmh": 60, "other": {"guid": GUIDS[1]}}),
            *starts_at(120, 200),
        ],
    )
    for minute, jumpers in ((0, ()), (2, (GUIDS[2],)), (4, ())):
        upload_log(round_, f"race_{minute}.log", race_log(minute, jumpers), champ_admin)

    data = api(champ_admin).get(f"/rounds/{round_.id}/restarts").json()
    assert [(a["number"], a["status"]) for a in data["attempts"]] == [
        (1, "abandoned"),
        (2, "abandoned"),
        (3, "active"),
    ]
    first, second = sorted(Restart.objects.all(), key=lambda r: r.abandoned_attempt.number)
    assert first.reason == Restart.Reason.FIRST_LAP_CRASH
    assert first.responsibility == Restart.Responsibility.DRIVERS
    assert list(first.responsible_entries.all()) == [d2]
    assert first.elapsed_seconds == 120
    assert second.reason == Restart.Reason.FALSE_START
    assert list(second.responsible_entries.all()) == [d3]
    assert second.review_status == "pending"  # A steward still confirms it.
    assert data["summary"]["total"] == 2
    assert AuditEntry.objects.filter(action="restart.detected").count() == 1

    # A second look creates nothing new.
    api(champ_admin).get(f"/rounds/{round_.id}/restarts")
    assert Restart.objects.count() == 2


def test_a_start_with_no_evidence_has_no_responsible(api, champ_admin, round_):
    collector(round_, champ_admin, starts_at(0, 90))
    api(champ_admin).get(f"/rounds/{round_.id}/restarts")
    restart = Restart.objects.get()
    assert restart.reason == Restart.Reason.OTHER
    assert restart.responsibility == Restart.Responsibility.UNKNOWN
    assert not restart.responsible_entries.exists()


def test_recorded_restarts_are_kept_and_only_the_missing_ones_come(api, champ_admin, round_):
    client = api(champ_admin)
    client.post(f"/rounds/{round_.id}/restarts", {"reason": "server_problem"})
    collector(round_, champ_admin, starts_at(0, 60, 150))
    client.get(f"/rounds/{round_.id}/restarts")
    restarts = sorted(Restart.objects.all(), key=lambda r: r.abandoned_attempt.number)
    assert [r.reason for r in restarts] == ["server_problem", "other"]
    assert restarts[1].elapsed_seconds == 90


def test_one_race_start_gives_no_restart(api, champ_admin, round_):
    collector(round_, champ_admin, starts_at(0))
    api(champ_admin).get(f"/rounds/{round_.id}/restarts")
    assert not Restart.objects.exists()
    assert Round.objects.count() == 1
