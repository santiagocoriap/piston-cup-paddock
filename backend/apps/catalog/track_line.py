"""Read the racing line of a track from the game file ai/fast_lane.ai.

The file has a header of 4 integers (version, point count, lap time, sample count). Each point
then has 5 values of 4 bytes: the world x, y, z, the distance from the start line in meters, and
the point number. The world x and z are the same as in the positions of the server collector.
"""

import json
import math
import struct

HEADER = struct.Struct("<4i")
POINT = struct.Struct("<4fi")
MIN_POINTS = 50
MAX_POINTS = 100_000
# The map keeps about 800 points: enough for a sharp drawing of any track.
KEEP_POINTS = 800


def read_line(data: bytes | None) -> dict | None:
    """The map of the track, or None when the data is not a good AI line:
    {"length_m": meters, "spline": [0..1], "x": [...], "z": [...]}."""
    if not data or len(data) < HEADER.size:
        return None
    _, count, _, _ = HEADER.unpack_from(data)
    if not MIN_POINTS <= count <= MAX_POINTS:
        return None
    if len(data) < HEADER.size + count * POINT.size:
        return None
    points = [POINT.unpack_from(data, HEADER.size + index * POINT.size) for index in range(count)]
    if not all(math.isfinite(value) for point in points for value in point[:4]):
        return None
    length = points[-1][3]
    if length <= 0 or any(b[3] < a[3] for a, b in zip(points, points[1:], strict=False)):
        return None
    step = max(1, count // KEEP_POINTS)
    kept = points[::step]
    return {
        "length_m": round(length),
        "spline": [round(p[3] / length, 5) for p in kept],
        "x": [round(p[0], 2) for p in kept],
        "z": [round(p[2], 2) for p in kept],
    }


def line_bytes(line: dict) -> bytes:
    return json.dumps(line, separators=(",", ":")).encode()
