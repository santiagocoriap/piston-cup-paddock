"""AI race reports: facts first, the AI only writes the text. LiteLLM is mocked."""

from types import SimpleNamespace

import pytest

from apps.competition.models import Round, SeasonEntry
from apps.identity.models import DriverProfile
from apps.reports import services
from apps.reports.models import RaceReport
from apps.reports.prompt import PROMPT_VERSION
from apps.reports.services import generate


class FakeAI:
    def __init__(self, configured=True, text="Gran carrera.", error=None):
        self.configured = configured
        self.text = text
        self.error = error
        self.calls = []

    def validate_environment(self, model):
        return {"keys_in_environment": self.configured, "missing_keys": []}

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(services, "litellm", fake)
    return fake


@pytest.fixture
def entries(season, car, driver_user):
    rows = []
    for n in range(1, 4):
        driver = DriverProfile.objects.create(
            display_name=f"Driver {n}", user=driver_user if n == 1 else None
        )
        rows.append(SeasonEntry.objects.create(season=season, driver=driver, car=car, number=n))
    return rows


@pytest.fixture
def raced(api, champ_admin, season, layout, entries):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    admin = api(champ_admin)
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    # A restart with a claimed driver, still pending.
    admin.post(
        f"/rounds/{round_.id}/restarts",
        {
            "reason": "first_lap_crash",
            "responsibility": "drivers",
            "driver_entry_ids": [entries[2].id],
        },
    )
    admin.put(f"/rounds/{round_.id}/result", {"lines": lines})
    return round_


def request(api, user, round_, **body):
    return api(user).post(f"/rounds/{round_.id}/reports", body)


def test_facts_have_sources_and_pending_restarts_have_no_names(api, champ_admin, raced, ai):
    data = request(api, champ_admin, raced).json()
    facts = data["reports"][0]["facts"]
    assert facts["result"]["status"] == "provisional"
    assert [row["driver"] for row in facts["classification"]] == [
        "Driver 1",
        "Driver 2",
        "Driver 3",
    ]
    for row in facts["classification"] + facts["standings"]:
        assert row["ref"]
    restart = facts["restarts"]["items"][0]
    assert restart["review_status"] == "pending"
    assert restart["responsibility"] == "not_decided"
    assert restart["responsible_drivers"] == []
    assert "Driver 3" not in str(facts["restarts"])


def test_worker_writes_the_text_and_stores_how(api, champ_admin, raced, ai, settings):
    settings.AI_REPORT_MODEL = "anthropic/test-model"
    request(api, champ_admin, raced, language="en", tone="roast")
    report = generate(RaceReport.objects.get().id)
    assert report.status == "ready"
    assert report.text == "Gran carrera."
    assert (report.prompt_version, report.model, report.language) == (
        PROMPT_VERSION,
        "anthropic/test-model",
        "en",
    )
    assert report.source_version.number == 1
    sent = ai.calls[0]["messages"]
    assert "not_decided" in sent[0]["content"]
    assert "English" in sent[1]["content"] and "Driver 1" in sent[1]["content"]


def test_workspace_id_goes_as_a_header(api, champ_admin, raced, ai, settings):
    settings.ANTHROPIC_WORKSPACE_ID = "wrkspc_1"
    request(api, champ_admin, raced)
    generate(RaceReport.objects.get().id)
    assert ai.calls[0]["extra_headers"] == {"anthropic-workspace-id": "wrkspc_1"}


def test_no_api_key_fails_the_report_but_not_the_results(api, champ_admin, raced, ai):
    ai.configured = False
    request(api, champ_admin, raced)
    report = generate(RaceReport.objects.get().id)
    assert (report.status, report.error) == ("failed", "ai_not_configured")
    assert api(champ_admin).get(f"/rounds/{raced.id}").json()["result"]


def test_provider_error_fails_only_the_report(api, champ_admin, raced, ai):
    ai.error = TimeoutError("slow")
    request(api, champ_admin, raced)
    report = generate(RaceReport.objects.get().id)
    assert report.status == "failed"
    assert report.error == "ai_error"
    approve = api(champ_admin).post(f"/rounds/{raced.id}/result/approve")
    assert approve.status_code == 200


def test_new_badge_until_the_driver_reads_that_version(api, champ_admin, driver_user, raced, ai):
    request(api, champ_admin, raced)
    first = generate(RaceReport.objects.get().id)
    driver = api(driver_user)
    assert driver.get(f"/rounds/{raced.id}/reports").json()["reports"][0]["unread"] is True
    assert driver.get("/dashboard").json()["seasons"][0]["new_reports"][0]["round_id"] == raced.id

    driver.post(f"/reports/{first.id}/read")
    assert driver.get(f"/rounds/{raced.id}/reports").json()["reports"][0]["unread"] is False
    assert driver.get("/dashboard").json()["seasons"][0]["new_reports"] == []

    request(api, champ_admin, raced)
    generate(RaceReport.objects.get(number=2).id)
    reports = driver.get(f"/rounds/{raced.id}/reports").json()["reports"]
    assert [(r["number"], r["unread"]) for r in reports] == [(2, True), (1, False)]


def test_driver_cannot_request_and_sees_only_ready_reports(
    api, champ_admin, driver_user, raced, ai
):
    assert request(api, driver_user, raced).status_code == 403
    request(api, champ_admin, raced)
    data = api(driver_user).get(f"/rounds/{raced.id}/reports").json()
    assert data["reports"] == []
    assert data["can_generate"] is False


def test_second_request_waits_for_the_first(api, champ_admin, raced, ai):
    request(api, champ_admin, raced)
    response = request(api, champ_admin, raced)
    assert response.json()["detail"] == "report_in_progress"


def test_round_without_result_cannot_have_a_report(api, champ_admin, season, layout, ai):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    assert request(api, champ_admin, round_).json()["detail"] == "result_required"


def test_approval_requests_a_report_only_with_a_key(api, champ_admin, raced, ai):
    ai.configured = False
    api(champ_admin).post(f"/rounds/{raced.id}/result/approve")
    assert RaceReport.objects.count() == 0
