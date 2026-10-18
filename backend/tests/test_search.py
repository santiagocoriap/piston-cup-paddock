from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile


def labels(response):
    return [(item["kind"], item["label"], item["path"]) for item in response.json()]


def test_search_finds_championships_seasons_rounds_and_drivers(
    api, league_admin, championship, season, layout, car
):
    round_ = Round.objects.create(season=season, number=3, track_layout=layout)
    driver = DriverProfile.objects.create(display_name="Ana Highlander")
    SeasonEntry.objects.create(season=season, driver=driver, car=car, number=7)

    found = labels(api(league_admin).get("/search?q=highl"))

    assert ("round", "Highlands · Long", f"/rounds/{round_.id}") in found
    assert (
        next(i for i in api(league_admin).get("/search?q=highl").json() if i["kind"] == "round")[
            "number"
        ]
        == 3
    )
    assert ("driver", "Ana Highlander", f"/drivers/{driver.id}") in found
    by_name = labels(api(league_admin).get("/search?q=lmdh"))
    assert ("championship", "LMDh", f"/championships/{championship.id}") in by_name
    assert ("season", "LMDh 2026", f"/seasons/{season.id}") in by_name


def test_search_needs_two_letters(api, league_admin, championship):
    assert api(league_admin).get("/search?q=l").json() == []


def test_search_shows_only_what_the_user_can_see(api, make_user, other_championship, league, car):
    from apps.competition.models import ChampionshipMember, Season

    hidden = Season.objects.create(
        championship=other_championship, name="2026", planned_round_count=4
    )
    stranger = DriverProfile.objects.create(display_name="Hidden Racer")
    SeasonEntry.objects.create(season=hidden, driver=stranger, car=car, number=1)
    outsider = make_user("outsider")
    from apps.competition.models import Championship

    mine = Championship.objects.create(league=league, name="Mine")
    ChampionshipMember.objects.create(
        championship=mine, user=outsider, role=ChampionshipMember.Role.DRIVER
    )

    assert labels(api(outsider).get("/search?q=gt3")) == []
    assert labels(api(outsider).get("/search?q=hidden")) == []
    assert labels(api(outsider).get("/search?q=mine")) == [
        ("championship", "Mine", f"/championships/{mine.id}")
    ]
