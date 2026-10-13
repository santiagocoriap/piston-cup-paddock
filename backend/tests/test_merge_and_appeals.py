"""Driver profile merge, protest evidence, and protest appeals."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEntry
from apps.competition.models import ChampionshipMember, Round, Season, SeasonEntry
from apps.identity.models import CareerAdjustment, DriverProfile
from apps.results.models import Protest


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


# Merge


def test_merge_moves_everything_to_the_kept_profile(api, league_admin, make_user, season, car):
    old = DriverProfile.objects.create(display_name="Juan viejo", steam_guid="76561190000000099")
    user = make_user("juan")
    kept = DriverProfile.objects.create(display_name="Juan", user=user)
    SeasonEntry.objects.create(season=season, driver=old, car=car, number=7)
    CareerAdjustment.objects.create(driver=old, kind="adjust", points=10, reason="x")
    response = api(league_admin).post(
        f"/drivers/{old.id}/merge", {"into_id": kept.id, "reason": "Duplicado"}
    )
    assert response.status_code == 200
    kept.refresh_from_db()
    assert kept.steam_guid == "76561190000000099" and kept.user == user
    assert SeasonEntry.objects.get().driver == kept
    assert CareerAdjustment.objects.get().driver == kept
    assert not DriverProfile.objects.filter(pk=old.id).exists()
    entry = AuditEntry.objects.get(action="driver.merged")
    assert entry.params == {"old": "Juan viejo", "kept": "Juan"} and entry.reason == "Duplicado"


def test_merge_refuses_conflicts(api, league_admin, make_user, season, car):
    a = DriverProfile.objects.create(display_name="A", user=make_user("a"))
    b = DriverProfile.objects.create(display_name="B", user=make_user("b"))
    client = api(league_admin)
    assert (
        client.post(f"/drivers/{a.id}/merge", {"into_id": b.id, "reason": "x"}).json()["detail"]
        == "both_have_accounts"
    )
    c = DriverProfile.objects.create(display_name="C")
    SeasonEntry.objects.create(season=season, driver=a, car=car, number=1)
    SeasonEntry.objects.create(season=season, driver=c, car=car, number=2)
    assert (
        client.post(f"/drivers/{c.id}/merge", {"into_id": a.id, "reason": "x"}).json()["detail"]
        == "both_in_season"
    )


def test_only_a_league_admin_merges(api, champ_admin):
    a = DriverProfile.objects.create(display_name="A")
    b = DriverProfile.objects.create(display_name="B")
    assert (
        api(champ_admin)
        .post(f"/drivers/{a.id}/merge", {"into_id": b.id, "reason": "x"})
        .status_code
        == 403
    )


# Protests


@pytest.fixture
def protest_setup(api, champ_admin, make_user, championship, season, layout, car):
    racer = make_user("racer")
    ChampionshipMember.objects.create(championship=championship, user=racer, role="driver")
    entries = [
        SeasonEntry.objects.create(
            season=season,
            driver=DriverProfile.objects.create(display_name=f"D{n}"),
            car=car,
            number=n,
        )
        for n in (1, 2)
    ]
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    lines = [
        {"entry_id": e.id, "status": "finished", "position": n}
        for n, e in enumerate(entries, start=1)
    ]
    api(champ_admin).put(f"/rounds/{round_.id}/result", {"lines": lines})
    api(racer).post(
        f"/rounds/{round_.id}/protests", {"description": "Me tocó", "entry_ids": [entries[1].id]}
    )
    return racer, round_, Protest.objects.get()


def test_author_adds_a_link_and_a_clip(api, protest_setup):
    racer, round_, protest = protest_setup
    client = api(racer)
    data = client.client.post(
        f"/api/protests/{protest.id}/evidence", {"url": "https://youtu.be/abc"}
    ).json()
    assert data["protests"][0]["evidence"][0]["url"] == "https://youtu.be/abc"
    clip = SimpleUploadedFile("t1.mp4", b"0" * 100, content_type="video/mp4")
    data = client.client.post(f"/api/protests/{protest.id}/evidence", {"file": clip}).json()
    evidence_id = data["protests"][0]["evidence"][1]["id"]
    assert client.client.get(f"/api/protest-evidence/{evidence_id}").status_code == 200
    bad = SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream")
    response = client.client.post(f"/api/protests/{protest.id}/evidence", {"file": bad})
    assert response.json()["detail"] == "evidence_type"


def test_stranger_cannot_see_a_clip(api, protest_setup, make_user):
    racer, _, protest = protest_setup
    clip = SimpleUploadedFile("t1.mp4", b"0" * 10, content_type="video/mp4")
    data = api(racer).client.post(f"/api/protests/{protest.id}/evidence", {"file": clip}).json()
    evidence_id = data["protests"][0]["evidence"][0]["id"]
    stranger = api(make_user("stranger"))
    assert stranger.client.get(f"/api/protest-evidence/{evidence_id}").status_code == 404


def test_one_appeal_with_another_decider(api, champ_admin, protest_setup, make_user, championship):
    racer, round_, protest = protest_setup
    admin = api(champ_admin)
    admin.post(
        f"/protests/{protest.id}/decision", {"outcome": "dismissed", "decision": "Incidente"}
    )
    detail = api(racer).get(f"/rounds/{round_.id}").json()["protests"][0]
    assert detail["can_appeal"] is True
    api(racer).post(f"/protests/{protest.id}/appeal", {"reason": "Hay video nuevo"})
    again = api(racer).post(f"/protests/{protest.id}/appeal", {"reason": "Otra vez"})
    assert again.json()["detail"] == "already_appealed"
    same = admin.post(
        f"/protests/{protest.id}/appeal-decision", {"outcome": "upheld", "decision": "x"}
    )
    assert same.json()["detail"] == "same_decider"
    steward = make_user("steward")
    ChampionshipMember.objects.create(championship=championship, user=steward, role="steward")
    data = (
        api(steward)
        .post(
            f"/protests/{protest.id}/appeal-decision",
            {"outcome": "upheld", "decision": "Tenía razón"},
        )
        .json()
    )
    appeal = data["protests"][0]
    assert (appeal["appeal_status"], appeal["appeal_decided_by"]) == ("upheld", "steward")


def test_only_the_author_appeals(api, champ_admin, protest_setup, make_user, championship):
    _, _, protest = protest_setup
    api(champ_admin).post(
        f"/protests/{protest.id}/decision", {"outcome": "dismissed", "decision": "No"}
    )
    other = make_user("other")
    ChampionshipMember.objects.create(championship=championship, user=other, role="driver")
    response = api(other).post(f"/protests/{protest.id}/appeal", {"reason": "x"})
    assert response.json()["detail"] == "only_author_appeals"
    assert Season.objects.count() == 1
