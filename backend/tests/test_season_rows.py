"""The season rows of the championship page, and the team standings."""

import pytest
from django.core.management import call_command

from apps.competition.models import Round
from apps.results.services import season_standings, team_standings


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    round_ = Round.objects.get()
    entries = list(round_.season.entries.order_by("number"))
    for index, entry in enumerate(entries):
        entry.team = "Rojo" if index % 2 == 0 else "Azul"
        entry.save()
    entries[-1].team = ""  # A driver with no team.
    entries[-1].save()
    return admin, round_


def test_team_points_are_the_sum_of_their_drivers(night):
    _, round_ = night
    season = round_.season
    by_entry = {row.entry_id: row.points for row in season_standings(season)}
    teams = {t.team: t for t in team_standings(season)}
    for name, team in teams.items():
        members = season.entries.filter(team=name)
        assert team.points == sum(by_entry[e.id] for e in members)
        assert len(team.drivers) == members.count()
    assert "" not in teams
    ranked = team_standings(season)
    assert [t.rank for t in ranked] == list(range(1, len(ranked) + 1))
    assert ranked[0].points >= ranked[-1].points


def test_the_season_row_has_the_podium_the_teams_and_the_last_winner(api, night):
    admin, round_ = night
    data = api(admin).get(f"/championships/{round_.season.championship_id}").json()
    row = data["progress"][0]
    assert len(row["podium"]) == 3
    assert row["podium"][0]["name"] == row["leader"]
    assert row["podium"][0]["points"] >= row["podium"][1]["points"]
    assert {t["name"] for t in row["teams"]} <= {"Rojo", "Azul"}
    assert row["last_round"]["number"] == round_.number
    assert row["last_round"]["winner"] == row["leader"]
    assert row["drivers"] == round_.season.entries.count()
    assert row["calendar"] == [
        {
            "round_id": round_.id,
            "number": round_.number,
            "track_name": round_.track_layout.track.name,
            "state": "done",
        }
    ]
    assert row["cars"]


def test_the_season_analysis_gives_the_team_of_each_driver(api, night):
    admin, round_ = night
    data = api(admin).get(f"/seasons/{round_.season_id}/analysis").json()
    assert {d["team"] for d in data["drivers"]} == {"Rojo", "Azul", ""}
