import pytest

from apps.competition.models import Round
from apps.reports.models import RaceReport


@pytest.fixture
def round_(season, layout):
    return Round.objects.create(
        season=season, number=1, track_layout=layout, scheduled_at="2026-10-18T00:00Z"
    )


def test_a_round_without_data_has_no_count_on_any_tab(api, driver_user, round_):
    data = api(driver_user).get(f"/rounds/{round_.id}/tab-counts").json()
    assert data == {
        "laps": 0,
        "incidents": 0,
        "replay": 0,
        "restarts": 0,
        "telemetry": 0,
        "reports": 0,
    }


def test_the_counts_show_the_restarts_and_the_ready_reports(api, champ_admin, round_):
    client = api(champ_admin)
    client.post(f"/rounds/{round_.id}/restarts", {"reason": "first_lap_crash"})
    client.post(f"/rounds/{round_.id}/restarts", {"reason": "server_problem"})
    RaceReport.objects.create(
        round=round_,
        season=round_.season,
        number=1,
        status=RaceReport.State.READY,
        language="es",
        text="Ok",
        facts={},
    )
    RaceReport.objects.create(
        round=round_,
        season=round_.season,
        number=2,
        status=RaceReport.State.PENDING,
        language="es",
        facts={},
    )

    data = client.get(f"/rounds/{round_.id}/tab-counts").json()
    assert data["restarts"] == 2
    assert data["reports"] == 1


def test_a_stranger_cannot_see_the_counts(api, make_user, round_):
    stranger = make_user("stranger")
    assert api(stranger).get(f"/rounds/{round_.id}/tab-counts").status_code == 404
