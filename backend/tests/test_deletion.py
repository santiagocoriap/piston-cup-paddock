"""Delete: a container goes with all inside it. A shared thing stays while something uses it."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.audit.models import AuditEntry
from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Championship, League, Round, Season, SeasonEntry
from apps.identity.models import DriverProfile
from apps.results.models import RaceResult


@pytest.fixture
def night(league_admin, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    league_admin.is_superuser = True  # The sample needs a first admin.
    league_admin.save()
    call_command("load_sample_night")
    return Championship.objects.get()


def gone(api, user, kind, object_id):
    return api(user).client.delete(f"/api/objects/{kind}/{object_id}")


def test_a_league_goes_with_its_full_race_night(api, league_admin, night):
    assert RaceResult.objects.exists()
    league = night.league
    response = gone(api, league_admin, "league", league.id)
    assert response.status_code == 200, response.json()
    assert not League.objects.filter(pk=league.pk).exists()
    assert not Championship.objects.exists()
    assert not Round.objects.exists() and not RaceResult.objects.exists()
    # The catalog and the drivers stay: other leagues can use them.
    assert Track.objects.exists() and Car.objects.exists() and DriverProfile.objects.exists()
    assert AuditEntry.objects.filter(action="league.deleted").exists()


def test_a_used_track_car_or_driver_stays(api, league_admin, night):
    layout = Round.objects.first().track_layout
    response = gone(api, league_admin, "track", layout.track_id)
    assert response.status_code == 409
    assert response.json()["detail"] == "in_use" and response.json()["uses"]
    entry = SeasonEntry.objects.first()
    assert gone(api, league_admin, "car", entry.car_id).status_code == 409
    assert gone(api, league_admin, "driver", entry.driver_id).status_code == 409
    # An entry with results stays too.
    assert gone(api, league_admin, "entry", entry.id).json()["detail"] == "entry_has_results"


def test_a_free_track_and_a_round_go(api, league_admin, champ_admin, season, layout):
    round_ = Round.objects.create(season=season, number=1, track_layout=layout)
    assert gone(api, champ_admin, "round", round_.id).status_code == 200
    assert gone(api, league_admin, "track", layout.track_id).status_code == 200
    assert not TrackLayout.objects.exists()


def test_who_can_delete(api, league_admin, champ_admin, driver_user, season, championship):
    assert gone(api, driver_user, "season", season.id).status_code == 403
    # A championship admin deletes a season, but not the championship.
    assert gone(api, champ_admin, "championship", championship.id).status_code == 403
    assert gone(api, champ_admin, "season", season.id).status_code == 200
    assert not Season.objects.exists()
    assert gone(api, league_admin, "championship", championship.id).status_code == 200


def test_a_user_goes_and_the_driver_profile_stays(api, league_admin, driver_user):
    driver = DriverProfile.objects.create(display_name="Ana", user=driver_user)
    assert gone(api, league_admin, "user", driver_user.id).status_code == 200
    driver.refresh_from_db()
    assert driver.user is None
    assert gone(api, league_admin, "user", league_admin.id).json()["detail"] == "delete_self"
    assert get_user_model().objects.filter(pk=league_admin.pk).exists()


def test_an_unknown_kind_or_id(api, league_admin):
    assert gone(api, league_admin, "planet", 1).status_code == 404
    assert gone(api, league_admin, "league", 999).status_code == 404
