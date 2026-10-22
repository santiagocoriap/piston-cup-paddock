import pytest
from django.test import Client

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Championship, ChampionshipMember, League, Season
from apps.identity.models import User


class Api:
    """A signed-in test client that sends and reads JSON."""

    def __init__(self, user=None):
        self.client = Client()
        if user:
            self.client.force_login(user)

    def get(self, path):
        return self.client.get(f"/api{path}")

    def post(self, path, data=None):
        return self.client.post(f"/api{path}", data or {}, content_type="application/json")

    def put(self, path, data):
        return self.client.put(f"/api{path}", data, content_type="application/json")

    def patch(self, path, data):
        return self.client.patch(f"/api{path}", data, content_type="application/json")

    def delete(self, path):
        return self.client.delete(f"/api{path}")


@pytest.fixture(autouse=True)
def no_github(settings):
    """The tests never ask GitHub for collector releases."""
    settings.COLLECTOR_RELEASE_REPO = ""


@pytest.fixture(autouse=True)
def fast_passwords(settings):
    """A fast hash for tests only. Production keeps the strong default hash."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def api():
    return Api


@pytest.fixture
def make_user(db):
    def make(username, **fields):
        return User.objects.create_user(username=username, password="unused-pass-1234", **fields)

    return make


@pytest.fixture
def league_admin(make_user):
    return make_user("boss", is_staff=True)


@pytest.fixture
def league(db):
    return League.objects.create(name="Piston Cup")


@pytest.fixture
def championship(league):
    return Championship.objects.create(league=league, name="LMDh")


@pytest.fixture
def other_championship(league):
    return Championship.objects.create(league=league, name="GT3")


@pytest.fixture
def season(championship):
    return Season.objects.create(championship=championship, name="2026", planned_round_count=8)


def _member(user, championship, role):
    ChampionshipMember.objects.create(championship=championship, user=user, role=role)
    return user


@pytest.fixture
def champ_admin(make_user, championship):
    return _member(make_user("organizer"), championship, ChampionshipMember.Role.ADMIN)


@pytest.fixture
def driver_user(make_user, championship):
    return _member(make_user("racer"), championship, ChampionshipMember.Role.DRIVER)


@pytest.fixture
def layout(db):
    track = Track.objects.create(key="ks_highlands", name="Highlands")
    return TrackLayout.objects.create(track=track, key="layout_long", name="Long")


@pytest.fixture
def car(db):
    return Car.objects.create(key="trr_lmdh_acura_arx-06", name="Acura ARX-06")
