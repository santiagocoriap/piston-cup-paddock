import pytest

from apps.audit.models import AuditEntry
from apps.audit.services import record
from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile


def test_season_round_and_result_changes_make_entries(api, champ_admin, championship, layout, car):
    client = api(champ_admin)
    season = client.post(
        f"/championships/{championship.id}/seasons", {"name": "2026", "planned_round_count": 8}
    ).json()
    round_ = client.post(
        f"/seasons/{season['id']}/rounds",
        {"track_layout_id": layout.id, "scheduled_at": "2026-10-18T21:30:00-03:00"},
    ).json()
    driver = DriverProfile.objects.create(display_name="Bing")
    entry = SeasonEntry.objects.create(season_id=season["id"], driver=driver, car=car, number=93)
    path = f"/rounds/{round_['id']}/result"
    line = {"entry_id": entry.id, "status": "finished", "position": 1}
    client.put(path, {"lines": [line]})
    client.put(path, {"lines": [{**line, "status": "dnf"}], "reason": "Abandonó en la vuelta 9"})

    actions = list(AuditEntry.objects.order_by("id").values_list("action", flat=True))
    assert actions == ["season.created", "round.created", "result.saved", "result.changed"]

    changed = AuditEntry.objects.get(action="result.changed")
    assert changed.actor == champ_admin
    assert changed.reason == "Abandonó en la vuelta 9"
    assert (changed.target_type, changed.target_id) == ("round", round_["id"])
    assert changed.changes == [
        {
            "field": "Bing",
            "old": {"status": "finished", "position": 1, "points": 25},
            "new": {"status": "dnf", "position": 1, "points": 25},
        }
    ]


def test_audit_refuses_a_password_field(champ_admin):
    with pytest.raises(ValueError):
        record(champ_admin, "user.changed", "user", 1, params={"password": "x"})
    with pytest.raises(ValueError):
        record(champ_admin, "user.changed", "user", 1, changes=[{"field": "a", "token": "x"}])


def test_championship_admin_sees_only_own_entries(
    api, champ_admin, championship, other_championship
):
    record(champ_admin, "season.created", "season", 1, championship=championship)
    record(champ_admin, "season.created", "season", 2, championship=other_championship)
    entries = api(champ_admin).get("/audit").json()
    assert [e["target_id"] for e in entries] == [1]
    assert entries[0]["championship_name"] == "LMDh"


def test_league_admin_sees_every_entry(api, league_admin, championship, other_championship):
    record(league_admin, "season.created", "season", 1, championship=championship)
    record(league_admin, "season.created", "season", 2, championship=other_championship)
    assert len(api(league_admin).get("/audit").json()) == 2


def test_driver_cannot_read_the_audit(api, driver_user):
    assert api(driver_user).get("/audit").status_code == 403


def test_member_role_change_keeps_old_and_new_role(api, champ_admin, championship, make_user):
    newcomer = make_user("newcomer")
    client = api(champ_admin)
    path = f"/championships/{championship.id}/members"
    client.put(path, {"user_id": newcomer.id, "role": "driver"})
    client.put(path, {"user_id": newcomer.id, "role": "admin"})
    last = AuditEntry.objects.filter(action="member.set").order_by("-id").first()
    assert last.changes == [{"field": "role", "old": "driver", "new": "admin"}]


def test_round_creation_stores_the_track_and_date(api, champ_admin, season, layout):
    api(champ_admin).post(
        f"/seasons/{season.id}/rounds",
        {"track_layout_id": layout.id, "scheduled_at": "2026-10-18T21:30:00-03:00"},
    )
    entry = AuditEntry.objects.get(action="round.created")
    assert entry.params["track"] == "Highlands - Long"
    assert entry.target_id == Round.objects.get().id
