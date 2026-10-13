"""Season tools: clone a season, replace a calendar track, and cancel a round."""

import pytest

from apps.catalog.models import Track, TrackLayout
from apps.competition.models import Round, Season, SeasonEntry
from apps.identity.models import DriverProfile
from apps.rules.models import RulesVersion

RULES = {
    "points_by_position": [10, 8, 6],
    "pole_bonus": 1,
    "fastest_lap_bonus": 0,
    "ballast_steps": [10, 10, 5, 3],
    "restrictor_steps": [2, 2, 1],
    "ballast_cap": 45,
    "restrictor_cap": 5,
    "ballast_reduction": 3,
    "restrictor_reduction": 1,
}


@pytest.fixture
def raced(api, champ_admin, season, layout, car):
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
            team="Red" if n == 1 else "",
        )
        for n in (1, 2)
    ]
    admin = api(champ_admin)
    rounds = []
    for number in (1, 2):
        round_ = Round.objects.create(season=season, number=number, track_layout=layout)
        lines = [
            {"entry_id": e.id, "status": "finished", "position": n}
            for n, e in enumerate(entries, start=1)
        ]
        admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
        rounds.append(round_)
    return entries, rounds


def test_cancelled_round_gives_no_points_and_no_handicap(api, champ_admin, season, raced):
    entries, rounds = raced
    client = api(champ_admin)
    before = client.get(f"/seasons/{season.id}/standings").json()
    assert before[0]["points"] == 50
    data = client.post(f"/rounds/{rounds[1].id}/cancel", {"reason": "Servidor caído"}).json()
    assert (data["cancelled"], data["cancel_reason"]) == (True, "Servidor caído")
    after = client.get(f"/seasons/{season.id}/standings").json()
    assert after[0]["points"] == 25
    handicaps = client.get(f"/seasons/{season.id}/handicaps").json()
    winner = next(e for e in handicaps["entries"] if e["entry_id"] == entries[0].id)
    assert winner["next_kg"] == 10  # One win counts, not two.
    title = client.get(f"/seasons/{season.id}/title").json()
    assert title["remaining_rounds"] == 8 - 1 - 1

    client.post(f"/rounds/{rounds[1].id}/restore", {"reason": "Error"})
    assert client.get(f"/seasons/{season.id}/standings").json()[0]["points"] == 50


def test_replace_track_keeps_the_history(api, champ_admin, season, layout):
    round_ = Round.objects.create(season=season, number=3, track_layout=layout)
    other = TrackLayout.objects.create(
        track=Track.objects.create(key="spa", name="Spa"), key="", name="GP"
    )
    client = api(champ_admin)
    data = client.post(
        f"/rounds/{round_.id}/replace-track",
        {"track_layout_id": other.id, "reason": "Mod roto"},
    ).json()
    assert data["track_name"] == "Spa"
    assert data["track_changes"][0]["reason"] == "Mod roto"
    assert data["track_changes"][0]["old_layout"] == str(layout)


def test_round_with_result_keeps_its_track(api, champ_admin, raced, layout):
    _, rounds = raced
    other = TrackLayout.objects.create(
        track=Track.objects.create(key="spa", name="Spa"), key="", name="GP"
    )
    response = api(champ_admin).post(
        f"/rounds/{rounds[0].id}/replace-track", {"track_layout_id": other.id, "reason": "x"}
    )
    assert response.json()["detail"] == "round_has_result"


def test_clone_copies_entries_rules_and_fixed_tracks(api, champ_admin, season, layout, raced):
    client = api(champ_admin)
    client.post(f"/seasons/{season.id}/rules", {**RULES, "reason": "Nuevas"})
    Round.objects.create(season=season, number=5, track_layout=layout, origin="fixed")
    response = client.post(f"/seasons/{season.id}/clone", {"name": "2027"})
    assert response.status_code == 201
    new = Season.objects.get(name="2027")
    assert [(e.number, e.team) for e in new.entries.order_by("number")] == [(1, "Red"), (2, "")]
    rules = RulesVersion.current_for(new)
    assert (rules.number, rules.points_by_position, rules.pole_bonus) == (1, [10, 8, 6], 1)
    assert [(r.number, r.origin, r.scheduled_at) for r in new.rounds.all()] == [(5, "fixed", None)]
    assert client.post(f"/seasons/{season.id}/clone", {"name": "2027"}).status_code == 409


def test_driver_cannot_cancel(api, driver_user, raced):
    _, rounds = raced
    response = api(driver_user).post(f"/rounds/{rounds[0].id}/cancel", {"reason": "x"})
    assert response.status_code == 403
