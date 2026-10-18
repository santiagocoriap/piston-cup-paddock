"""The team names of the season entries become teams of their league."""

from django.db import migrations


def fill(apps, schema_editor):
    entry_model = apps.get_model("competition", "SeasonEntry")
    team_model = apps.get_model("competition", "Team")
    for league_id, name in (
        entry_model.objects.exclude(team="")
        .values_list("season__championship__league_id", "team")
        .distinct()
    ):
        if not team_model.objects.filter(league_id=league_id, name__iexact=name).exists():
            team_model.objects.create(league_id=league_id, name=name)


class Migration(migrations.Migration):
    dependencies = [("competition", "0013_teams")]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
