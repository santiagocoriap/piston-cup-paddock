"""The script once lost the samples of a lap when the lap-completed event came late. These laps
have only a few samples, and the charts show a short line. They go to the admin review."""

import json

from django.db import migrations


def flag(apps, schema_editor):
    from apps.telemetry.samples import covers_lap

    lap_model = apps.get_model("telemetry", "TelemetryLap")
    for lap in lap_model.objects.filter(source="script", match="league").iterator():
        try:
            with lap.samples.open("rb") as handle:
                channels = json.loads(handle.read())
        except (OSError, ValueError):
            continue  # A missing file stays missing.
        if not covers_lap(channels, lap.lap_time_ms):
            lap.match = "flagged"
            lap.issues = ["partial_samples"]
            lap.round = None
            lap.save(update_fields=["match", "issues", "round"])


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0010_lap_samples_bytes")]

    operations = [migrations.RunPython(flag, migrations.RunPython.noop)]
