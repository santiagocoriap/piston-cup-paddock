"""Clean the samples of the laps that came before the finish line fix (samples.py)."""

import json

from django.core.files.base import ContentFile
from django.db import migrations


def trim(apps, schema_editor):
    from apps.telemetry.samples import trim_to_lap

    lap_model = apps.get_model("telemetry", "TelemetryLap")
    for lap in lap_model.objects.all().iterator():
        try:
            with lap.samples.open("rb") as handle:
                channels = json.loads(handle.read())
        except (OSError, ValueError):
            continue  # A missing file stays missing.
        if "t_ms" not in channels:
            continue
        clean = trim_to_lap(channels, lap.lap_time_ms)
        if len(clean["t_ms"]) < 2 or clean == channels:
            continue
        content = json.dumps(clean, separators=(",", ":"), sort_keys=True).encode()
        lap.samples.save("samples.json", ContentFile(content), save=False)
        lap.save(update_fields=["samples"])


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0004_remove_driver_key")]

    operations = [migrations.RunPython(trim, migrations.RunPython.noop)]
