from apps.catalog.models import Car
from apps.competition.models import Round, Season
from apps.identity.models import User
from apps.results.models import Protest, RaceResult
from apps.voting.models import Ballot


def kinds(response):
    return {item["kind"]: item for item in response.json()}


def test_admin_sees_what_waits_for_a_decision(api, champ_admin, season, layout):
    first = Round.objects.create(season=season, number=1, track_layout=layout)
    second = Round.objects.create(season=season, number=2, track_layout=layout)
    result = RaceResult.objects.create(round=first, status=RaceResult.State.PROVISIONAL)
    RaceResult.objects.create(round=second, status=RaceResult.State.OFFICIAL)
    Protest.objects.create(result=result, description="Contact in turn 1")
    Ballot.objects.create(season=season, title="Pistas 2027", status=Ballot.State.CLOSED)
    Ballot.objects.create(season=season, title="Clases", status=Ballot.State.OPEN)

    pending = kinds(api(champ_admin).get("/pending"))

    assert pending["results"]["count"] == 1
    assert pending["results"]["items"][0] == {
        "path": f"/rounds/{first.id}",
        "championship": "LMDh",
        "name": "Highlands · Long",
        "number": 1,
    }
    assert pending["protests"]["count"] == 1
    assert pending["ballots_closed"]["items"][0]["name"] == "Pistas 2027"
    assert pending["ballots_open"]["count"] == 1


def test_a_driver_sees_nothing(api, driver_user, season, layout):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    RaceResult.objects.create(round=round_)
    assert api(driver_user).get("/pending").json() == []


def test_an_admin_of_another_championship_does_not_see_these(
    api, make_user, other_championship, season, layout
):
    from apps.competition.models import ChampionshipMember

    other = make_user("other")
    ChampionshipMember.objects.create(
        championship=other_championship, user=other, role=ChampionshipMember.Role.ADMIN
    )
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    RaceResult.objects.create(round=round_)
    assert "results" not in kinds(api(other).get("/pending"))


def test_league_admin_sees_accounts_and_missing_images(api, league_admin, layout):
    waiting = User.objects.create_user(username="newbie")
    waiting.set_unusable_password()
    waiting.save()
    Car.objects.create(key="bmw", name="BMW")

    pending = kinds(api(league_admin).get("/pending"))

    assert pending["accounts"]["items"] == [
        {"path": "/admin/accounts", "championship": None, "name": "newbie", "number": None}
    ]
    assert pending["images"]["count"] == 2  # One layout and one car.
    assert pending["images"]["items"] == []


def test_championship_gives_the_latest_season_progress_and_next_round(
    api, champ_admin, championship, layout
):
    old = Season.objects.create(championship=championship, name="2025", planned_round_count=4)
    season = Season.objects.create(championship=championship, name="2026", planned_round_count=8)
    Round.objects.create(season=old, number=1, track_layout=layout)
    first = Round.objects.create(season=season, number=1, track_layout=layout)
    second = Round.objects.create(season=season, number=2, track_layout=layout)
    RaceResult.objects.create(round=first, status=RaceResult.State.OFFICIAL)

    latest = api(champ_admin).get(f"/championships/{championship.id}").json()["latest"]

    assert latest["season_id"] == season.id
    assert (latest["done"], latest["total"]) == (1, 8)
    assert latest["next_round"]["round_id"] == second.id
    assert latest["next_round"]["number"] == 2
    assert latest["leader"] is None  # No result lines yet.


def test_championship_with_no_season_has_no_latest(api, champ_admin, championship):
    assert api(champ_admin).get(f"/championships/{championship.id}").json()["latest"] is None
