import pytest

from apps.audit.models import AuditEntry
from apps.catalog.models import Car, CarClass, Track, TrackLayout
from apps.competition.models import (
    Championship,
    ChampionshipMember,
    ChampionshipRole,
    League,
    Round,
    Season,
    SeasonEntry,
)
from apps.identity.models import DriverProfile
from apps.voting.models import Ballot

pytestmark = pytest.mark.django_db


def test_deleting_a_championship_keeps_the_audit_and_says_who(api, league_admin, season):
    AuditEntry.objects.create(
        actor_name="x", action="season.created", championship=season.championship,
        championship_name="LMDh", target_type="season", target_id=season.id,
    )
    response = api(league_admin).delete(f"/championships/{season.championship_id}")
    assert response.status_code == 204
    assert not Championship.objects.exists()
    assert not Season.objects.exists()
    deleted = AuditEntry.objects.get(action="championship.deleted")
    assert deleted.actor_name == "boss"
    assert deleted.params["name"] == "LMDh"
    assert AuditEntry.objects.filter(action="season.deleted", actor_name="boss").exists()
    # The old entry stays, with the name but without the link.
    old = AuditEntry.objects.get(action="season.created")
    assert old.championship_id is None
    assert old.championship_name == "LMDh"


def test_only_a_league_admin_deletes_a_championship(api, champ_admin, championship):
    assert api(champ_admin).delete(f"/championships/{championship.id}").status_code == 403
    assert Championship.objects.filter(pk=championship.pk).exists()


def test_deleting_a_league_deletes_its_championships(api, league_admin, season):
    response = api(league_admin).delete(f"/leagues/{season.championship.league_id}")
    assert response.status_code == 204
    assert not League.objects.exists()
    assert not Championship.objects.exists()
    actions = set(AuditEntry.objects.values_list("action", flat=True))
    assert {"league.deleted", "championship.deleted", "season.deleted"} <= actions


def test_a_championship_admin_deletes_a_season_and_a_round_without_result(
    api, champ_admin, season, layout
):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    client = api(champ_admin)
    assert client.delete(f"/rounds/{round_.id}").status_code == 204
    assert client.delete(f"/seasons/{season.id}").status_code == 204
    assert AuditEntry.objects.filter(action="round.deleted", actor_name="organizer").exists()
    assert AuditEntry.objects.filter(action="season.deleted", actor_name="organizer").exists()


def test_a_driver_cannot_delete_a_season(api, driver_user, season):
    assert api(driver_user).delete(f"/seasons/{season.id}").status_code == 403


def test_entry_member_and_role_deletes(api, champ_admin, driver_user, season, car, championship):
    driver = DriverProfile.objects.create(display_name="Ana")
    entry = SeasonEntry.objects.create(season=season, driver=driver, car=car, number=7)
    role = ChampionshipRole.objects.create(championship=championship, name="Media")
    client = api(champ_admin)
    assert client.delete(f"/entries/{entry.id}").status_code == 204
    assert client.delete(f"/championships/{championship.id}/members/{driver_user.id}").status_code == 204
    assert not ChampionshipMember.objects.filter(user=driver_user).exists()
    assert client.delete(f"/roles/{role.id}").status_code == 204
    actions = set(AuditEntry.objects.values_list("action", flat=True))
    assert {"entry.deleted", "member.removed", "role.deleted"} <= actions


def test_a_role_with_members_stays(api, champ_admin, driver_user, championship):
    role = ChampionshipRole.objects.create(championship=championship, name="Media")
    ChampionshipMember.objects.filter(user=driver_user).update(
        role=ChampionshipMember.Role.CUSTOM, custom_role=role
    )
    response = api(champ_admin).delete(f"/roles/{role.id}")
    assert response.status_code == 409
    assert ChampionshipRole.objects.filter(pk=role.pk).exists()
    assert not AuditEntry.objects.filter(action="role.deleted").exists()


def test_a_track_car_class_and_driver_in_use_stay(api, champ_admin, season, layout, car):
    driver = DriverProfile.objects.create(display_name="Ana")
    SeasonEntry.objects.create(season=season, driver=driver, car=car, number=7)
    Round.objects.create(season=season, number=1, track_layout=layout)
    client = api(champ_admin)
    assert client.delete(f"/catalog/layouts/{layout.id}").status_code == 409
    assert client.delete(f"/catalog/tracks/{layout.track_id}").status_code == 409
    assert client.delete(f"/catalog/cars/{car.id}").status_code == 409
    assert client.delete(f"/drivers/{driver.id}").status_code == 409
    assert Track.objects.exists() and TrackLayout.objects.exists()
    assert Car.objects.exists() and DriverProfile.objects.exists()
    assert not AuditEntry.objects.filter(action__endswith=".deleted").exists()


def test_unused_catalog_items_and_drivers_are_deleted(api, champ_admin, layout, car):
    driver = DriverProfile.objects.create(display_name="Ana")
    car_class = CarClass.objects.create(name="GT3")
    client = api(champ_admin)
    assert client.delete(f"/catalog/tracks/{layout.track_id}").status_code == 204
    assert client.delete(f"/catalog/cars/{car.id}").status_code == 204
    assert client.delete(f"/catalog/classes/{car_class.id}").status_code == 204
    assert client.delete(f"/drivers/{driver.id}").status_code == 204
    assert not Track.objects.exists() and not TrackLayout.objects.exists()
    actions = set(AuditEntry.objects.values_list("action", flat=True))
    assert {"track.deleted", "layout.deleted", "car.deleted", "class.deleted", "driver.deleted"} <= actions


def test_a_driver_cannot_delete_a_car(api, driver_user, car):
    assert api(driver_user).delete(f"/catalog/cars/{car.id}").status_code == 403


def test_ballot_delete_and_decided_ballot_stays(api, champ_admin, season):
    draft = Ballot.objects.create(season=season, kind="track", title="Vote")
    decided = Ballot.objects.create(
        season=season, kind="track", title="Done", status=Ballot.State.DECIDED
    )
    client = api(champ_admin)
    assert client.delete(f"/ballots/{draft.id}").status_code == 204
    assert client.delete(f"/ballots/{decided.id}").status_code == 422
    assert AuditEntry.objects.filter(action="ballot.deleted", actor_name="organizer").exists()
