"""Save a telemetry lap for a test, as the Paddock script does after a match."""

import json
import uuid
from datetime import datetime

from django.core.files.base import ContentFile

from apps.telemetry.models import TelemetryLap


def save_lap(driver, round_, channels: dict, **fields) -> TelemetryLap:
    values = {
        "session_type": "race",
        "track": "ks_highlands",
        "car": "acura",
        "lap_number": 3,
        "lap_time_ms": 189296,
        "valid": True,
        "recorded_at": datetime.fromisoformat("2026-10-11T22:35:00+00:00"),
        "sample_hz": 20,
        **fields,
    }
    lap = TelemetryLap(
        driver=driver,
        round=round_,
        championship=round_.season.championship if round_ else None,
        source=TelemetryLap.Source.SCRIPT,
        sha256=uuid.uuid4().hex,
        uploaded_by=driver.user,
        **values,
    )
    lap.samples.save("samples.json", ContentFile(json.dumps(channels).encode()), save=False)
    lap.save()
    return lap
