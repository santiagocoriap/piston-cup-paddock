"""Clean the samples of one lap.

At the finish line, the game can give one sample of the wrong lap: the last sample of a lap can
already have the time of the next lap (a few ms), and the first sample of a lap can still have
the time of the lap before. A chart then draws a line back across the whole lap. This module
keeps only the samples of the lap itself, in time order.
"""

import gzip
import json

SLACK_MS = 200  # A sample can come a little after the lap time.
MIN_COVERAGE = 0.8  # The samples of a good lap cover at least this part of the lap time.


def trim_to_lap(channels: dict[str, list], lap_time_ms: int) -> dict[str, list]:
    times = channels["t_ms"]
    keep = [i for i, t in enumerate(times) if 0 <= t <= lap_time_ms + SLACK_MS]
    # After a step back in time, only the last run of samples belongs to the lap.
    start = 0
    for position in range(1, len(keep)):
        if times[keep[position]] < times[keep[position - 1]]:
            start = position
    # A step back near the end is a sample of the next lap: keep the run before it.
    run = keep[start:]
    if start and len(keep[:start]) > len(run):
        run = keep[:start]
    # The last sample can be past the line already: the position goes from 0.99 to 0.0.
    positions = channels.get("pos")
    while positions and len(run) > 2 and positions[run[-1]] < 0.05 < 0.95 < positions[run[-2]]:
        run = run[:-1]
    return {name: [values[i] for i in run] for name, values in channels.items()}


def read_samples(handle) -> dict[str, list]:
    """The channels of a stored file. A new file has gzip compression, and an old file has none."""
    data = handle.read()
    return json.loads(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def pack_samples(channels: dict[str, list]) -> bytes:
    content = json.dumps(channels, separators=(",", ":"), sort_keys=True).encode()
    return gzip.compress(content, mtime=0)


def covers_lap(channels: dict[str, list], lap_time_ms: int) -> bool:
    """False for a lap with samples of only a part of the lap time."""
    times = channels.get("t_ms") or []
    return bool(times) and times[-1] - times[0] >= lap_time_ms * MIN_COVERAGE


def trim_stored_laps(lap_model) -> None:
    """Clean the samples of the stored laps. The data migrations use it."""
    from django.core.files.base import ContentFile

    for lap in lap_model.objects.all().iterator():
        try:
            with lap.samples.open("rb") as handle:
                channels = read_samples(handle)
        except (OSError, ValueError):
            continue  # A missing file stays missing.
        if "t_ms" not in channels:
            continue
        clean = trim_to_lap(channels, lap.lap_time_ms)
        if len(clean["t_ms"]) < 2 or clean == channels:
            continue
        lap.samples.save("samples.json", ContentFile(pack_samples(clean)), save=False)
        lap.save(update_fields=["samples"])
