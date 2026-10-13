"""Rules editor: versions, preview against old results, future-only or recalculated."""

import pytest

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.results.models import RaceResult, ResultVersion
from apps.rules.models import RulesVersion

RULES = {
    "points_by_position": [10, 8, 6],
    "pole_bonus": 0,
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
        )
        for n in (1, 2, 3)
    ]
    admin = api(champ_admin)
    # Round 1: D1 wins. Round 2: D2 wins and D1 is third.
    for number, order in ((1, (0, 1, 2)), (2, (1, 2, 0))):
        round_ = Round.objects.create(season=season, number=number, track_layout=layout)
        lines = [
            {"entry_id": entries[i].id, "status": "finished", "position": p}
            for p, i in enumerate(order, start=1)
        ]
        admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
    return entries


def test_versions_start_with_the_defaults(api, champ_admin, season, raced):
    data = api(champ_admin).get(f"/seasons/{season.id}/rules").json()
    assert data["can_edit"] is True
    assert [v["number"] for v in data["versions"]] == [1]


def test_preview_shows_new_points_and_changes_nothing(api, champ_admin, season, raced):
    before = api(champ_admin).get(f"/seasons/{season.id}/standings").json()
    rows = api(champ_admin).post(f"/seasons/{season.id}/rules/preview", RULES).json()
    by_name = {r["driver_name"]: r for r in rows}
    assert (by_name["D1"]["current_points"], by_name["D1"]["new_points"]) == (25 + 15, 10 + 6)
    assert by_name["D2"]["new_points"] == 8 + 10
    # D2 leads now (18 + 25 = 43) and still leads with the new rules (8 + 10 = 18).
    assert (by_name["D2"]["current_rank"], by_name["D2"]["current_points"]) == (1, 43)
    assert (by_name["D2"]["new_rank"], by_name["D1"]["new_rank"]) == (1, 2)
    assert api(champ_admin).get(f"/seasons/{season.id}/standings").json() == before
    assert RulesVersion.objects.count() == 1


def test_future_only_change_keeps_old_results(api, champ_admin, season, raced):
    response = api(champ_admin).post(
        f"/seasons/{season.id}/rules", {**RULES, "reason": "Menos puntos", "recalculate": False}
    )
    versions = response.json()["versions"]
    assert (versions[0]["number"], versions[0]["reason"]) == (2, "Menos puntos")
    assert versions[0]["recalculated"] is False
    assert ResultVersion.objects.count() == 2  # No new result versions.
    standings = api(champ_admin).get(f"/seasons/{season.id}/standings").json()
    assert standings[0]["points"] == 43


def test_recalculated_change_writes_new_versions(api, champ_admin, season, raced):
    api(champ_admin).post(
        f"/seasons/{season.id}/rules", {**RULES, "reason": "Corregir", "recalculate": True}
    )
    for result in RaceResult.objects.all():
        assert result.current_version.rules_version.number == 2
        assert result.current_version.kind == "correction"
    standings = api(champ_admin).get(f"/seasons/{season.id}/standings").json()
    assert (standings[0]["points"], standings[1]["points"]) == (18, 16)


def test_driver_cannot_preview_or_change(api, driver_user, season, raced):
    client = api(driver_user)
    assert client.post(f"/seasons/{season.id}/rules/preview", RULES).status_code == 403
    assert client.post(f"/seasons/{season.id}/rules", {**RULES, "reason": "x"}).status_code == 403
    assert client.get(f"/seasons/{season.id}/rules").json()["can_edit"] is False


def test_values_out_of_range_are_refused(api, champ_admin, season, raced):
    bad = {**RULES, "points_by_position": [500]}
    response = api(champ_admin).post(f"/seasons/{season.id}/rules/preview", bad)
    assert response.json()["detail"] == "rules_value_out_of_range"
