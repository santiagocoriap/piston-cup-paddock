"""Clean the samples of one lap.

At the finish line, the game can give one sample of the wrong lap: the last sample of a lap can
already have the time of the next lap (a few ms), and the first sample of a lap can still have
the time of the lap before. A chart then draws a line back across the whole lap. This module
keeps only the samples of the lap itself, in time order.
"""

SLACK_MS = 200  # A sample can come a little after the lap time.


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
    return {name: [values[i] for i in run] for name, values in channels.items()}
