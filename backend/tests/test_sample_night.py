"""The demo data command loads the sample race night with the normal import steps."""

import pytest
from django.core.management import CommandError, call_command

from apps.competition.models import Championship
from apps.restarts.models import Restart
from apps.results.models import RaceResult


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


def test_loads_the_night_and_can_load_it_again(make_user):
    make_user("admin", is_staff=True, is_superuser=True)
    call_command("load_sample_night")
    result = RaceResult.objects.get()
    assert result.status == "provisional"
    assert result.current_version.lines.count() == 5
    assert Restart.objects.count() == 20

    with pytest.raises(CommandError):
        call_command("load_sample_night")
    call_command("load_sample_night", "--reset")
    assert Championship.objects.filter(name="Demo LMDh").count() == 1
    assert Restart.objects.count() == 20


def test_needs_an_admin(db):
    with pytest.raises(CommandError):
        call_command("load_sample_night")
