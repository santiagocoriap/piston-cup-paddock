"""Attendance, calendar files, and notifications."""

from datetime import datetime, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.community.models import Notification
from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile


@pytest.fixture
def setup(make_user, championship, season, car, layout, champ_admin):
    racer = make_user("racer")
    ChampionshipMember.objects.create(
        championship=championship, user=racer, role=ChampionshipMember.Role.DRIVER
    )
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=name, user=user),
            car=car,
            number=n,
        )
        for n, (name, user) in enumerate((("Racer", racer), ("Other", None)), start=1)
    ]
    future = Round.objects.create(
        season=season,
        number=1,
        track_layout=layout,
        scheduled_at=timezone.now() + timedelta(days=3),
    )
    return racer, entries, future


def test_driver_answers_attendance_and_admin_sees_the_list(api, champ_admin, setup):
    racer, _, round_ = setup
    data = api(racer).put(f"/rounds/{round_.id}/attendance", {"answer": "yes"}).json()
    assert (data["mine"], data["yes"], data["can_answer"]) == ("yes", 1, True)
    rows = api(champ_admin).get(f"/rounds/{round_.id}/attendance").json()["rows"]
    assert {r["driver_name"]: r["answer"] for r in rows} == {"Racer": "yes", "Other": None}
    card = api(racer).get("/dashboard").json()["seasons"][0]["next_round"]
    assert (card["my_attendance"], card["attending"]) == ("yes", 1)


def test_no_answer_after_the_start_or_without_an_entry(api, champ_admin, setup):
    racer, _, round_ = setup
    assert (
        api(champ_admin).put(f"/rounds/{round_.id}/attendance", {"answer": "no"}).status_code == 403
    )
    round_.scheduled_at = timezone.now() - timedelta(hours=1)
    round_.save()
    response = api(racer).put(f"/rounds/{round_.id}/attendance", {"answer": "no"})
    assert response.json()["detail"] == "round_started"


def test_calendar_files(api, setup, season):
    racer, _, round_ = setup
    round_.scheduled_at = datetime(2026, 10, 18, 22, 0, tzinfo=timezone.UTC)
    round_.save()
    response = api(racer).client.get(f"/api/seasons/{season.id}/calendar.ics")
    text = response.content.decode()
    assert response["Content-Type"].startswith("text/calendar")
    assert "DTSTART:20261018T220000Z" in text and "DTEND:20261019T000000Z" in text
    assert f"UID:round-{round_.id}@piston-cup-paddock" in text
    assert api(racer).client.get(f"/api/rounds/{round_.id}/calendar.ics").status_code == 200


def test_private_feed_works_without_a_session_and_can_be_replaced(api, setup):
    racer, _, round_ = setup
    path = api(racer).get("/me/calendar-feed").json()["path"]
    assert "BEGIN:VEVENT" in Client().get(path).content.decode()
    new_path = api(racer).post("/me/calendar-feed").json()["path"]
    assert Client().get(path).status_code == 404
    assert Client().get(new_path).status_code == 200


def test_notifications_for_results_and_reading_them(api, champ_admin, setup):
    racer, entries, round_ = setup
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    api(champ_admin).put(f"/rounds/{round_.id}/result", {"lines": lines})
    api(champ_admin).post(f"/rounds/{round_.id}/result/approve")
    data = api(racer).get("/me/notifications").json()
    assert [n["kind"] for n in data["items"]] == ["result.official", "result.published"]
    assert data["unread"] == 2
    assert data["items"][0]["link"] == f"/rounds/{round_.id}"
    data = api(racer).post("/me/notifications/read", {"ids": []}).json()
    assert data["unread"] == 0


def test_protest_notifies_staff_and_then_the_author(api, champ_admin, setup):
    racer, entries, round_ = setup
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    api(champ_admin).put(f"/rounds/{round_.id}/result", {"lines": lines})
    Notification.objects.all().delete()
    api(racer).post(
        f"/rounds/{round_.id}/protests",
        {"description": "Me tocó", "entry_ids": [entries[1].id]},
    )
    assert Notification.objects.get().user == champ_admin
    protest_id = api(champ_admin).get(f"/rounds/{round_.id}").json()["protests"][0]["id"]
    api(champ_admin).post(
        f"/protests/{protest_id}/decision", {"outcome": "dismissed", "decision": "Incidente"}
    )
    mine = Notification.objects.filter(user=racer).get()
    assert (mine.kind, mine.params["outcome"]) == ("protest.decided", "dismissed")
