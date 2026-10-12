from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Track, TrackLayout
from apps.competition.models import ChampionshipMember, Round
from apps.voting.models import Ballot, Vote


@pytest.fixture
def layouts(db):
    result = []
    for key in ["spa", "monza", "imola", "suzuka", "fuji", "laguna", "bathurst", "brands"]:
        track = Track.objects.create(key=key, name=key.title())
        result.append(TrackLayout.objects.create(track=track, key="", name="GP"))
    return result


@pytest.fixture
def voters(make_user, championship):
    users = [make_user(name) for name in ["v1", "v2", "v3", "v4"]]
    for user in users:
        ChampionshipMember.objects.create(
            championship=championship, user=user, role=ChampionshipMember.Role.DRIVER
        )
    return users


@pytest.fixture
def admin(api, champ_admin):
    return api(champ_admin)


def fix(client, season, layout, **extra):
    return client.post(
        f"/seasons/{season.id}/fixed-rounds", {"track_layout_id": layout.id, **extra}
    )


def ballot(client, season, **settings):
    data = {"kind": "track", "title": "Pistas 2026", "method": "multiple", "selection_limit": 3}
    response = client.post(f"/seasons/{season.id}/ballots", {**data, **settings})
    assert response.status_code == 201, response.json()
    return response.json()


def add(client, ballot_id, layout=None, label=""):
    data = {"track_layout_id": layout.id} if layout else {"label": label}
    response = client.post(f"/ballots/{ballot_id}/options", data)
    assert response.status_code == 200, response.json()
    return response.json()


def option_ids(detail, *labels):
    by_label = {o["label"]: o["id"] for o in detail["options"]}
    return [by_label[label] for label in labels]


# Fixed tracks (#13)


def test_admin_reserves_fixed_tracks_with_optional_position_and_date(admin, season, layouts):
    first = fix(admin, season, layouts[0], number=1, scheduled_at="2026-11-01T21:00:00Z")
    second = fix(admin, season, layouts[1])
    assert first.status_code == second.status_code == 201
    assert (first.json()["origin"], first.json()["number"]) == ("fixed", 1)
    assert second.json()["scheduled_at"] is None
    detail = admin.get(f"/seasons/{season.id}").json()
    assert detail["voted_slots"] == 6  # Eight rounds, two fixed.


def test_more_fixed_rounds_than_the_season_total_are_refused(admin, season, layouts):
    season.planned_round_count = 2
    season.save()
    fix(admin, season, layouts[0])
    fix(admin, season, layouts[1])
    response = fix(admin, season, layouts[2])
    assert response.json()["detail"] == "too_many_fixed_rounds"


def test_fixed_layout_is_not_a_candidate_unless_repeats_are_allowed(admin, season, layouts):
    fix(admin, season, layouts[0])
    detail = ballot(admin, season)
    refused = admin.post(f"/ballots/{detail['id']}/options", {"track_layout_id": layouts[0].id})
    assert refused.json()["detail"] == "layout_is_fixed"
    admin.client.patch(
        f"/api/seasons/{season.id}/settings",
        {"allow_repeat_layouts": True},
        content_type="application/json",
    )
    assert (
        admin.post(
            f"/ballots/{detail['id']}/options", {"track_layout_id": layouts[0].id}
        ).status_code
        == 200
    )


def test_eight_rounds_with_two_fixed_tracks_vote_six_slots(api, admin, season, layouts, voters):
    fix(admin, season, layouts[0])
    fix(admin, season, layouts[1])
    detail = ballot(admin, season, selection_limit=6)
    for layout in layouts[2:]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    assert detail["slots"] == 6
    api(voters[0]).put(
        f"/ballots/{detail['id']}/vote", {"option_ids": [o["id"] for o in detail["options"]]}
    )
    admin.post(f"/ballots/{detail['id']}/close", {})
    rounds = admin.get(f"/seasons/{season.id}").json()["rounds"]
    assert [r["origin"] for r in rounds] == ["fixed", "fixed"] + ["voted"] * 6


def test_calendar_shows_origin_and_admin_sets_the_date(admin, season, layouts):
    round_ = fix(admin, season, layouts[0]).json()
    response = admin.client.patch(
        f"/api/rounds/{round_['id']}/calendar",
        {"scheduled_at": "2026-11-08T21:00:00Z", "number": 3},
        content_type="application/json",
    )
    assert response.json()["number"] == 3
    assert response.json()["scheduled_at"].startswith("2026-11-08T21:00:00")


# Ballot options (#14)


def test_admin_sets_method_limit_and_vote_power(api, admin, season, layouts, voters):
    detail = ballot(admin, season, selection_limit=2, power_overrides={str(voters[0].id): 3})
    for layout in layouts[:3]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    spa, monza, imola = option_ids(detail, "Spa - GP", "Monza - GP", "Imola - GP")

    too_many = api(voters[0]).put(
        f"/ballots/{detail['id']}/vote", {"option_ids": [spa, monza, imola]}
    )
    assert too_many.json()["detail"] == "too_many_choices"
    api(voters[0]).put(f"/ballots/{detail['id']}/vote", {"option_ids": [spa]})
    api(voters[1]).put(f"/ballots/{detail['id']}/vote", {"option_ids": [monza, imola]})
    counts = {
        o["label"]: o["votes"] for o in admin.get(f"/ballots/{detail['id']}").json()["options"]
    }
    assert counts == {"Spa - GP": 3, "Monza - GP": 1, "Imola - GP": 1}
    mine = api(voters[0]).get(f"/ballots/{detail['id']}").json()
    assert mine["my_power"] == 3


def test_single_choice_allows_one_option(api, admin, season, layouts, voters):
    detail = ballot(admin, season, method="single", selection_limit=5)
    assert detail["selection_limit"] == 1
    for layout in layouts[:2]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    both = [o["id"] for o in detail["options"]]
    assert (
        api(voters[0]).put(f"/ballots/{detail['id']}/vote", {"option_ids": both}).json()["detail"]
        == "too_many_choices"
    )


def test_voter_list_is_frozen_when_the_ballot_opens(
    api, admin, season, layouts, voters, make_user, championship
):
    detail = ballot(admin, season)
    detail = add(admin, detail["id"], layouts[0])
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    late = make_user("late")
    ChampionshipMember.objects.create(championship=championship, user=late, role="driver")
    response = api(late).put(
        f"/ballots/{detail['id']}/vote", {"option_ids": [detail["options"][0]["id"]]}
    )
    assert response.json()["detail"] == "not_a_voter"
    assert (
        admin.get(f"/ballots/{detail['id']}").json()["voter_count"] == 5
    )  # 4 drivers and 1 admin.


def test_prior_season_threshold_limits_the_voters(
    admin, season, layouts, voters, championship, layout, car
):
    from apps.competition.models import Season, SeasonEntry
    from apps.identity.models import DriverProfile

    previous = Season.objects.create(championship=championship, name="2025", planned_round_count=1)
    entry = SeasonEntry.objects.create(
        season=previous,
        driver=DriverProfile.objects.create(display_name="V1", user=voters[0]),
        car=car,
        number=1,
    )
    round_ = Round.objects.create(season=previous, number=1, track_layout=layout)
    admin.put(
        f"/rounds/{round_.id}/result",
        {"lines": [{"entry_id": entry.id, "status": "finished", "position": 1}]},
    )
    detail = ballot(admin, season, prior_season_id=previous.id, min_prior_starts=1)
    detail = add(admin, detail["id"], layouts[0])
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    assert detail["voter_count"] == 1
    assert detail["voters"][0]["username"] == "v1"


@pytest.mark.parametrize(
    ("totals_visibility", "choice_visibility", "before_close", "after_close", "names"),
    [
        ("live", "visible", True, True, True),
        ("after_close", "visible", False, True, True),
        ("hidden", "hidden", False, False, False),
        ("live", "hidden", True, True, False),
    ],
)
def test_visibility_for_drivers(
    api,
    admin,
    season,
    layouts,
    voters,
    totals_visibility,
    choice_visibility,
    before_close,
    after_close,
    names,
):
    detail = ballot(
        admin, season, totals_visibility=totals_visibility, choice_visibility=choice_visibility
    )
    detail = add(admin, detail["id"], layouts[0])
    detail = add(admin, detail["id"], layouts[1])
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    driver = api(voters[0])
    driver.put(f"/ballots/{detail['id']}/vote", {"option_ids": [detail["options"][0]["id"]]})
    seen = driver.get(f"/ballots/{detail['id']}").json()
    assert (seen["options"][0]["votes"] is not None) == before_close
    admin.post(f"/ballots/{detail['id']}/close", {})
    seen = driver.get(f"/ballots/{detail['id']}").json()
    assert (seen["options"][0]["votes"] is not None) == after_close
    assert (seen["options"][0]["voters"] is not None) == (names and after_close)
    assert admin.get(f"/ballots/{detail['id']}").json()["options"][0]["votes"] is not None


def test_tie_for_the_last_slots_starts_a_runoff_with_only_the_tied_options(
    api, admin, season, layouts, voters
):
    season.planned_round_count = 2
    season.save()
    detail = ballot(admin, season, selection_limit=1)
    for layout in layouts[:4]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    spa, monza, imola, suzuka = option_ids(
        detail, "Spa - GP", "Monza - GP", "Imola - GP", "Suzuka - GP"
    )
    for voter, choice in zip(voters, [spa, spa, monza, imola], strict=True):
        api(voter).put(f"/ballots/{detail['id']}/vote", {"option_ids": [choice]})
    closed = admin.post(f"/ballots/{detail['id']}/close", {}).json()
    assert closed["status"] == "closed"
    assert sorted(closed["tie"]["option_ids"]) == sorted([monza, imola])
    assert closed["tie"]["open_slots"] == 1

    runoff = admin.post(f"/ballots/{detail['id']}/runoff").json()
    assert sorted(o["label"] for o in runoff["options"]) == ["Imola - GP", "Monza - GP"]
    imola_runoff = option_ids(runoff, "Imola - GP")[0]
    api(voters[0]).put(f"/ballots/{runoff['id']}/vote", {"option_ids": [imola_runoff]})
    admin.post(f"/ballots/{runoff['id']}/close", {})

    parent = admin.get(f"/ballots/{detail['id']}").json()
    assert parent["status"] == "decided"
    assert {o["label"] for o in parent["options"] if o["selected"]} == {"Spa - GP", "Imola - GP"}
    labels = [r["track_name"] for r in admin.get(f"/seasons/{season.id}").json()["rounds"]]
    assert sorted(labels) == ["Imola", "Spa"]


def test_runoff_limit_is_respected(api, admin, season, layouts, voters):
    season.planned_round_count = 1
    season.save()
    detail = ballot(admin, season, selection_limit=1, max_runoffs=0)
    for layout in layouts[:2]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    closed = admin.post(f"/ballots/{detail['id']}/close", {}).json()
    assert closed["tie"] is not None
    assert admin.post(f"/ballots/{detail['id']}/runoff").json()["detail"] == "runoff_limit_reached"


def test_admin_closes_early_with_a_reason_and_the_votes_stay(api, admin, season, layouts, voters):
    season.planned_round_count = 1
    season.save()
    later = (timezone.now() + timedelta(days=3)).isoformat()
    detail = ballot(admin, season, selection_limit=1, closes_at=later)
    for layout in layouts[:2]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    spa, monza = option_ids(detail, "Spa - GP", "Monza - GP")
    api(voters[0]).put(f"/ballots/{detail['id']}/vote", {"option_ids": [spa]})

    refused = admin.post(f"/ballots/{detail['id']}/close", {})
    assert refused.json()["detail"] == "reason_required"
    decided = admin.post(
        f"/ballots/{detail['id']}/decide",
        {"option_ids": [monza], "reason": "Spa no está disponible"},
    ).json()
    assert decided["status"] == "decided"
    assert decided["closed_early"] is True
    assert [o["selected_by"] for o in decided["options"] if o["selected"]] == ["admin"]
    assert Vote.objects.count() == 1


def test_car_class_ballot_selects_classes(api, admin, season, voters):
    detail = ballot(admin, season, kind="car_class", title="Clase 2026", method="single", slots=1)
    for label in ["LMDh", "GT3"]:
        detail = add(admin, detail["id"], label=label)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    lmdh = option_ids(detail, "LMDh")[0]
    for voter in voters[:2]:
        api(voter).put(f"/ballots/{detail['id']}/vote", {"option_ids": [lmdh]})
    admin.post(f"/ballots/{detail['id']}/close", {})
    summary = admin.get(f"/seasons/{season.id}/ballots").json()
    assert summary[0]["winners"] == ["LMDh"]
    assert Round.objects.count() == 0


def test_vote_change_can_be_blocked(api, admin, season, layouts, voters):
    detail = ballot(admin, season, allow_vote_changes=False)
    for layout in layouts[:2]:
        detail = add(admin, detail["id"], layout)
    detail = admin.post(f"/ballots/{detail['id']}/open").json()
    spa, monza = option_ids(detail, "Spa - GP", "Monza - GP")
    client = api(voters[0])
    client.put(f"/ballots/{detail['id']}/vote", {"option_ids": [spa]})
    assert client.put(f"/ballots/{detail['id']}/vote", {"option_ids": [monza]}).json()[
        "detail"
    ] == ("vote_change_not_allowed")


def test_driver_cannot_manage_a_ballot(api, admin, season, layouts, voters):
    detail = ballot(admin, season)
    client = api(voters[0])
    assert client.post(f"/ballots/{detail['id']}/open").status_code == 403
    assert (
        client.post(f"/seasons/{season.id}/ballots", {"kind": "track", "title": "x"}).status_code
        == 403
    )
    assert Ballot.objects.count() == 1


def test_prior_season_must_be_in_the_same_championship(admin, season, other_championship):
    from apps.competition.models import Season

    foreign = Season.objects.create(
        championship=other_championship, name="X", planned_round_count=1
    )
    for season_id in (foreign.id, 999999, season.id):
        response = admin.post(
            f"/seasons/{season.id}/ballots",
            {"kind": "track", "title": "x", "prior_season_id": season_id, "min_prior_starts": 1},
        )
        assert response.json()["detail"] == "bad_prior_season"
