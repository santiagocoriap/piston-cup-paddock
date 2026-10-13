"""Season reports: facts from official rounds only. LiteLLM is mocked."""

import pytest
from django.core.management import call_command

from apps.competition.models import ChampionshipMember, Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.reports import services
from apps.reports.models import RaceReport
from apps.reports.prompt import SEASON_PROMPT_VERSION
from apps.reports.services import generate
from apps.restarts.models import Restart

from .test_reports import FakeAI


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI(text="Temporada de locos.")
    monkeypatch.setattr(services, "litellm", fake)
    return fake


@pytest.fixture
def night(make_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    return admin, Round.objects.get()


def request(api, user, season, **body):
    return api(user).post(f"/seasons/{season.id}/reports", body)


def test_needs_an_official_round(api, night, ai):
    admin, round_ = night
    response = request(api, admin, round_.season)
    assert response.json()["detail"] == "official_rounds_required"


def test_facts_from_official_rounds(api, night, ai):
    admin, round_ = night
    client = api(admin)
    client.post(f"/rounds/{round_.id}/result/approve")
    restart = Restart.objects.first()
    restart.review_status = Restart.Review.CONFIRMED
    restart.responsibility = Restart.Responsibility.DRIVERS
    restart.save()
    restart.responsible_entries.set([SeasonEntry.objects.get(driver__display_name="Driver 04")])

    data = request(api, admin, round_.season, language="es").json()
    facts = data["reports"][0]["facts"]
    assert facts["season"]["official_rounds"] == 1
    assert facts["season"]["finished"] is False
    assert facts["champion"] == []  # Seven rounds remain.
    leader = facts["standings"][0]
    assert (leader["driver"], leader["wins"], leader["podiums"], leader["starts"]) == (
        "Driver 01",
        1,
        1,
        1,
    )
    assert facts["rounds"][0]["winner"] == "Driver 01"
    assert facts["rounds"][0]["fastest_lap"]["time"] == "3:09.296"
    assert facts["restarts"]["confirmed_caused"] == [
        {"driver": "Driver 04", "restarts": 1, "shared": 0}
    ]
    assert "no_race_details" not in facts["data_gaps"]

    report = generate(RaceReport.objects.get(kind="season").id)
    assert report.status == "ready"
    assert report.prompt_version == SEASON_PROMPT_VERSION
    assert "season report" in ai.calls[0]["messages"][0]["content"]


def test_standings_only_season_has_no_race_details(api, champ_admin, season, layout, car, ai):
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
        )
        for n in (1, 2)
    ]
    admin = api(champ_admin)
    for number in (1, 2):
        round_ = Round.objects.create(season=season, number=number, track_layout=layout)
        lines = [
            {"entry_id": e.id, "status": "finished", "position": n}
            for n, e in enumerate(entries, start=1)
        ]
        admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
        admin.post(f"/rounds/{round_.id}/result/approve")
    facts = request(api, champ_admin, season).json()["reports"][0]["facts"]
    assert "no_race_details" in facts["data_gaps"]
    assert [s["points"] for s in facts["standings"]] == [50, 36]


def test_driver_sees_ready_season_reports_with_new_badge(api, night, make_user, ai):
    admin, round_ = night
    season = round_.season
    driver_user = make_user("racer")
    ChampionshipMember.objects.create(
        championship=season.championship, user=driver_user, role=ChampionshipMember.Role.DRIVER
    )
    api(admin).post(f"/rounds/{round_.id}/result/approve")
    request(api, admin, season)
    report = generate(RaceReport.objects.get(kind="season").id)
    driver = api(driver_user)
    assert request(api, driver_user, season).status_code == 403
    listed = driver.get(f"/seasons/{season.id}/reports").json()["reports"]
    assert [(r["id"], r["unread"]) for r in listed] == [(report.id, True)]
    driver.post(f"/reports/{report.id}/read")
    assert driver.get(f"/seasons/{season.id}/reports").json()["reports"][0]["unread"] is False
    # A season report is not a race report of the round.
    assert driver.get(f"/rounds/{round_.id}/reports").json()["reports"] == []
