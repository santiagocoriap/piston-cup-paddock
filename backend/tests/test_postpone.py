"""Move a round to the next week: the later rounds with no result move with it."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.audit.models import AuditEntry
from apps.competition.models import Round
from apps.results.models import RaceResult

BA = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture
def calendar(season, layout):
    league = season.championship.league
    league.timezone = "America/Argentina/Buenos_Aires"
    league.save()
    start = datetime(2026, 11, 8, 18, 0, tzinfo=BA)
    rounds = [
        Round.objects.create(
            season=season, number=n, track_layout=layout, scheduled_at=start + timedelta(weeks=n)
        )
        for n in range(1, 5)
    ]
    rounds.append(Round.objects.create(season=season, number=5, track_layout=layout))
    return rounds


def test_a_round_and_the_later_rounds_move_one_week(api, champ_admin, calendar):
    first, second, third, fourth, no_date = calendar
    before = {r.id: r.scheduled_at for r in calendar}
    response = api(champ_admin).post(f"/rounds/{second.id}/postpone", {"weeks": 1})
    assert response.status_code == 200
    assert [r["number"] for r in response.json()] == [2, 3, 4]
    for item in (second, third, fourth):
        item.refresh_from_db()
        assert item.scheduled_at == before[item.id] + timedelta(weeks=1)
        assert item.scheduled_at.astimezone(BA).hour == 18  # The same clock time.
    first.refresh_from_db()
    assert first.scheduled_at == before[first.id]
    no_date.refresh_from_db()
    assert no_date.scheduled_at is None
    entry = AuditEntry.objects.get(action="round.postponed")
    assert entry.params["count"] == 3


def test_a_round_with_a_result_does_not_move(api, champ_admin, calendar):
    first = calendar[0]
    RaceResult.objects.create(round=first)
    assert api(champ_admin).post(f"/rounds/{first.id}/postpone", {"weeks": 1}).status_code == 409


def test_a_driver_cannot_move_a_round(api, driver_user, calendar):
    response = api(driver_user).post(f"/rounds/{calendar[1].id}/postpone", {"weeks": 1})
    assert response.status_code in (403, 404)
