"""Ballot schedules, reminders, minimum participation, voter names, track rules, vote audit."""

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditEntry
from apps.community.models import Notification
from apps.competition.models import SeasonEntry
from apps.identity.models import DriverProfile
from apps.voting.models import Ballot
from apps.voting.services import run_schedule

from .test_voting import add, admin, ballot, layouts, option_ids, voters  # noqa: F401


def label_ballot(client, season, **settings):
    settings = {"kind": "car_class", "title": "Clase", "slots": 1, **settings}
    detail = ballot(client, season, **settings)
    for label in ("GT3", "LMDh"):
        add(client, detail["id"], label=label)
    return detail["id"]


def test_worker_opens_reminds_and_closes_on_time(admin, season, voters):  # noqa: F811
    now = timezone.now()
    ballot_id = label_ballot(
        admin,
        season,
        opens_at=(now + timedelta(minutes=5)).isoformat(),
        closes_at=(now + timedelta(hours=10)).isoformat(),
        remind_hours_before=12,
    )
    assert run_schedule(now) == {"opened": 0, "reminded": 0, "closed": 0}
    assert run_schedule(now + timedelta(minutes=6)) == {"opened": 1, "reminded": 1, "closed": 0}
    assert Notification.objects.filter(kind="ballot.reminder").count() == 5  # 4 drivers, 1 admin
    assert run_schedule(now + timedelta(minutes=7))["reminded"] == 0  # Only one reminder.
    assert run_schedule(now + timedelta(hours=11))["closed"] == 1
    assert Ballot.objects.get(pk=ballot_id).status in ("closed", "decided")


def test_low_participation_closes_without_a_winner(api, admin, season, voters):  # noqa: F811
    ballot_id = label_ballot(admin, season, min_participation_pct=75)
    admin.post(f"/ballots/{ballot_id}/open")
    detail = admin.get(f"/ballots/{ballot_id}").json()
    api(voters[0]).put(f"/ballots/{ballot_id}/vote", {"option_ids": option_ids(detail, "GT3")})
    closed = admin.post(f"/ballots/{ballot_id}/close", {"reason": ""}).json()
    assert (closed["status"], closed["low_participation"]) == ("closed", True)
    assert not any(o["selected"] for o in closed["options"])
    assert closed["tie"] is None  # An admin decides, not a tie.


def test_count_anyway_keeps_the_winner(api, admin, season, voters):  # noqa: F811
    ballot_id = label_ballot(
        admin, season, min_participation_pct=75, low_participation_action="count"
    )
    admin.post(f"/ballots/{ballot_id}/open")
    detail = admin.get(f"/ballots/{ballot_id}").json()
    api(voters[0]).put(f"/ballots/{ballot_id}/vote", {"option_ids": option_ids(detail, "GT3")})
    closed = admin.post(f"/ballots/{ballot_id}/close", {"reason": ""}).json()
    assert closed["status"] == "decided"


def test_voter_names_only_when_the_ballot_shows_them(api, admin, season, voters):  # noqa: F811
    hidden = label_ballot(admin, season)
    shown = label_ballot(admin, season, title="Clase 2", show_voter_names=True)
    for ballot_id in (hidden, shown):
        admin.post(f"/ballots/{ballot_id}/open")
        detail = admin.get(f"/ballots/{ballot_id}").json()
        api(voters[0]).put(f"/ballots/{ballot_id}/vote", {"option_ids": option_ids(detail, "GT3")})
    assert api(voters[1]).get(f"/ballots/{hidden}").json()["voted_names"] is None
    assert api(voters[1]).get(f"/ballots/{shown}").json()["voted_names"] == ["v1"]


def test_excluded_venue_and_small_grid_are_refused(admin, season, layouts, car):  # noqa: F811
    for n in range(1, 4):
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
        )
    detail = ballot(admin, season, excluded_track_ids=[layouts[0].track_id])
    response = admin.post(f"/ballots/{detail['id']}/options", {"track_layout_id": layouts[0].id})
    assert response.json()["detail"] == "track_excluded"
    layouts[1].pit_boxes = 2
    layouts[1].save()
    response = admin.post(f"/ballots/{detail['id']}/options", {"track_layout_id": layouts[1].id})
    assert response.json()["detail"] == "grid_too_small"


def test_vote_audit_keeps_a_hidden_choice_secret(api, admin, season, voters):  # noqa: F811
    ballot_id = label_ballot(admin, season, choice_visibility="hidden")
    admin.post(f"/ballots/{ballot_id}/open")
    detail = admin.get(f"/ballots/{ballot_id}").json()
    api(voters[0]).put(f"/ballots/{ballot_id}/vote", {"option_ids": option_ids(detail, "LMDh")})
    entry = AuditEntry.objects.get(action="ballot.voted")
    assert entry.actor == voters[0]
    assert entry.changes == []
    assert "LMDh" not in str(entry.params)


def test_admin_reminds_now(admin, season, voters):  # noqa: F811
    ballot_id = label_ballot(admin, season)
    admin.post(f"/ballots/{ballot_id}/open")
    detail = admin.post(f"/ballots/{ballot_id}/remind").json()
    assert detail["reminded_at"] is not None
    assert Notification.objects.filter(kind="ballot.reminder").count() == 5  # 4 drivers, 1 admin


def test_ballot_gives_the_championship_for_the_breadcrumbs(admin, season):  # noqa: F811
    ballot_id = label_ballot(admin, season)
    detail = admin.get(f"/ballots/{ballot_id}").json()
    assert detail["championship_id"] == season.championship_id
