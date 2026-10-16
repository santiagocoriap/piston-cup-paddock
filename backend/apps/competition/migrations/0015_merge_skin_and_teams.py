from django.db import migrations


class Migration(migrations.Migration):
    """The skin choice and the teams were made on two branches, both after 0012."""

    dependencies = [
        ("competition", "0013_seasonentry_skin"),
        ("competition", "0014_teams_from_entries"),
    ]

    operations = []
