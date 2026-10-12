# Move result lines into versions, and add penalties and protests.
# Each existing result becomes version 1 of its result, and keeps its lines and points.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

STATUS_CHOICES = [
    ("finished", "Finished"),
    ("dnf", "Did not finish"),
    ("dns", "Did not start"),
    ("dsq", "Disqualified"),
]


def lines_into_versions(apps, schema_editor):
    RaceResult = apps.get_model("results", "RaceResult")
    ResultVersion = apps.get_model("results", "ResultVersion")
    ResultLine = apps.get_model("results", "ResultLine")
    for result in RaceResult.objects.all():
        version = ResultVersion.objects.create(
            result=result,
            number=1,
            kind="entry",
            rules_version_id=result.rules_version_id,
            created_by_id=result.updated_by_id,
        )
        for line in ResultLine.objects.filter(result=result):
            line.version = version
            line.entered_status = line.status
            line.entered_position = line.position
            line.save(update_fields=["version", "entered_status", "entered_position"])
        result.current_version = version
        result.published_at = result.updated_at
        result.save(update_fields=["current_version", "published_at"])


def user_fk(**extra):
    return models.ForeignKey(
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="+",
        to=settings.AUTH_USER_MODEL,
        **extra,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0003_season_protest_window_minutes"),
        ("results", "0002_initial"),
        ("rules", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResultVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveSmallIntegerField()),
                (
                    "kind",
                    models.CharField(
                        choices=[("entry", "First entry"), ("correction", "Correction"), ("penalty", "Penalty")],
                        max_length=12,
                    ),
                ),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", user_fk(blank=True, null=True)),
                (
                    "result",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="results.raceresult",
                    ),
                ),
                (
                    "rules_version",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="rules.rulesversion"),
                ),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.AddConstraint(
            model_name="resultversion",
            constraint=models.UniqueConstraint(fields=("result", "number"), name="unique_result_version"),
        ),
        migrations.AddField(
            model_name="raceresult",
            name="status",
            field=models.CharField(
                choices=[("provisional", "Provisional"), ("under_review", "Under review"), ("official", "Official")],
                default="provisional",
                max_length=14,
            ),
        ),
        migrations.AddField(
            model_name="raceresult", name="published_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="raceresult", name="approved_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(model_name="raceresult", name="approved_by", field=user_fk(blank=True, null=True)),
        migrations.AddField(
            model_name="raceresult",
            name="current_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="results.resultversion",
            ),
        ),
        migrations.AddField(
            model_name="resultline",
            name="version",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lines",
                to="results.resultversion",
            ),
        ),
        migrations.AddField(
            model_name="resultline",
            name="entered_status",
            field=models.CharField(default="finished", max_length=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="resultline",
            name="entered_position",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(lines_into_versions, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="resultline", name="unique_entry_per_result"),
        migrations.RemoveField(model_name="resultline", name="result"),
        migrations.RemoveField(model_name="raceresult", name="rules_version"),
        migrations.RemoveField(model_name="raceresult", name="updated_by"),
        migrations.AlterField(
            model_name="resultline",
            name="version",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lines",
                to="results.resultversion",
            ),
        ),
        migrations.AlterField(
            model_name="resultline",
            name="entered_status",
            field=models.CharField(choices=STATUS_CHOICES, max_length=10),
        ),
        migrations.AddConstraint(
            model_name="resultline",
            constraint=models.UniqueConstraint(fields=("version", "entry"), name="unique_entry_per_version"),
        ),
        migrations.CreateModel(
            name="Protest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("lap", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("description", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("upheld", "Upheld"), ("dismissed", "Dismissed")],
                        default="open",
                        max_length=10,
                    ),
                ),
                ("decision", models.TextField(blank=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="competition.attempt"
                    ),
                ),
                ("decided_by", user_fk(blank=True, null=True)),
                (
                    "involved",
                    models.ManyToManyField(blank=True, related_name="protests", to="competition.seasonentry"),
                ),
                (
                    "result",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protests",
                        to="results.raceresult",
                    ),
                ),
                ("submitted_by", user_fk(null=True)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="Penalty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[("positions", "Lose positions"), ("points", "Lose points"), ("dsq", "Disqualification")],
                        max_length=10,
                    ),
                ),
                ("value", models.PositiveSmallIntegerField(default=0)),
                ("reason", models.TextField()),
                (
                    "source",
                    models.CharField(
                        choices=[("steward", "Steward decision"), ("imported", "Imported")],
                        default="steward",
                        max_length=10,
                    ),
                ),
                ("external_id", models.CharField(blank=True, max_length=100, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="competition.attempt"
                    ),
                ),
                ("created_by", user_fk(blank=True, null=True)),
                (
                    "entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="penalties",
                        to="competition.seasonentry",
                    ),
                ),
                (
                    "protest",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="penalties",
                        to="results.protest",
                    ),
                ),
                (
                    "result",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="penalties",
                        to="results.raceresult",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="penalty",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id__isnull", False)),
                fields=("result", "external_id"),
                name="unique_external_penalty",
            ),
        ),
    ]
