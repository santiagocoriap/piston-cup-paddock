"""Clean the end of the stored laps again: the last sample past the line (samples.py)."""

from django.db import migrations


def trim(apps, schema_editor):
    from apps.telemetry.samples import trim_stored_laps

    trim_stored_laps(apps.get_model("telemetry", "TelemetryLap"))


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0005_trim_lap_samples")]

    operations = [migrations.RunPython(trim, migrations.RunPython.noop)]
