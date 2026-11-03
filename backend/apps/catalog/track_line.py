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
CORNER_RADIUS_M = 120
CORNER_GAP_M = 60
HIGH_SPEED_PER_KM = 1.8
TECHNICAL_PER_KM = 2.8


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


def corner_count(line: dict) -> int:
    """The corners of the line: parts with a radius below CORNER_RADIUS_M. Two parts with less
    than CORNER_GAP_M between them are one corner."""
    length = line["length_m"]
    points = list(zip(line["spline"], line["x"], line["z"], strict=True))
    corners = 0
    in_corner = False
    straight = 0.0
    for before, here, after in zip(points, points[1:], points[2:], strict=False):
        first = math.atan2(here[2] - before[2], here[1] - before[1])
        second = math.atan2(after[2] - here[2], after[1] - here[1])
        turn = abs((second - first + math.pi) % (2 * math.pi) - math.pi)
        distance = (after[0] - before[0]) * length / 2
        radius = distance / turn if turn > 0 else math.inf
        if radius < CORNER_RADIUS_M:
            corners += not in_corner
            in_corner = True
            straight = 0.0
        elif in_corner:
            straight += distance
            if straight >= CORNER_GAP_M:
                in_corner = False
    return corners


def circuit_type(line: dict) -> tuple[str, int]:
    """The kind of track from its corners for each km: (kind, corners). "high_speed" has few
    corners, "technical" has many, and "mixed" is between them."""
    corners = corner_count(line)
    per_km = corners / max(line["length_m"] / 1000, 0.1)
    kind = (
        "high_speed"
        if per_km < HIGH_SPEED_PER_KM
        else "technical"
        if per_km > TECHNICAL_PER_KM
        else "mixed"
    )
    return kind, corners


def line_bytes(line: dict) -> bytes:
    return json.dumps(line, separators=(",", ":")).encode()
