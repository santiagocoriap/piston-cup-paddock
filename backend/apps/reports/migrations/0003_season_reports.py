import django.db.models.deletion
from django.db import migrations, models


def fill_season(apps, schema_editor):
    RaceReport = apps.get_model("reports", "RaceReport")
    for report in RaceReport.objects.select_related("round"):
        report.season_id = report.round.season_id
        report.save(update_fields=["season"])


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0006_league_timezone"),
        ("reports", "0002_sarcastic_tone"),
    ]

    operations = [
        migrations.AddField(
            model_name="racereport",
            name="kind",
            field=models.CharField(
                choices=[("race", "Race report"), ("season", "Season report")],
                default="race",
                max_length=6,
            ),
        ),
        migrations.AddField(
            model_name="racereport",
            name="season",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports",
                to="competition.season",
            ),
        ),
        migrations.RunPython(fill_season, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="racereport",
            name="season",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports",
                to="competition.season",
            ),
        ),
        migrations.AlterField(
            model_name="racereport",
            name="round",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports",
                to="competition.round",
            ),
        ),
        migrations.RemoveConstraint(model_name="racereport", name="unique_report_number"),
        migrations.AddConstraint(
            model_name="racereport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "race")),
                fields=("round", "number"),
                name="unique_report_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="racereport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "season")),
                fields=("season", "number"),
                name="unique_season_report_number",
            ),
        ),
    ]
