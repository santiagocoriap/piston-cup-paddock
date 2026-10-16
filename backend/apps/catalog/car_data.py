"""Turn the files of a car's data folder (tyres.ini, engine.ini, power.lut, ...) into small JSON.

The app keeps the numbers, not the files. The result looks like this:

    {"ini": {"tyres": {"FRONT": {"NAME": "Slick Soft", "WIDTH": 0.3, ...}, ...}, ...},
     "lut": {"power": [[0, 0], [5000, 300], ...], ...}}

Files that only matter for the 3D game (sounds, cameras, lights, instruments) are left out.
"""

import re

MAX_LUT_POINTS = 64
MAX_SECTIONS = 200
MAX_KEYS = 200
SKIPPED = frozenset(
    {
        "ambient_shadows",
        "analog_instruments",
        "analog_speed_curve",
        "blurred_objects",
        "cameras",
        "colliders",
        "dash_cam",
        "desktop",
        "digital_instruments",
        "driver3d",
        "flame_presets",
        "flames",
        "lights",
        "lods",
        "mirrors",
        "proview_nodes",
        "sounds",
        "suspension_graphics",
        "wing_animations",
    }
)
NUMBER = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")
SECTION = re.compile(r"^\[([^\]]{1,80})\]")


def _value(text: str) -> int | float | str:
    """A number when the text is a number, else the text. Some mods leave a note after the number
    ("0.1778<tab>(1651)"); the game reads the first word, and so do we."""
    text = text.strip()
    first = text.split(None, 1)[0] if text else ""
    if NUMBER.match(first):
        text = first
    if NUMBER.match(text):
        number = float(text)
        return int(number) if number.is_integer() and "." not in text and "e" not in text.lower() else round(number, 6)
    return text[:200]


def parse_ini(data: bytes) -> dict[str, dict]:
    """{section: {KEY: value}}. Comments start with ; or //. A key that comes twice keeps the
    last value, as the game does."""
    result: dict[str, dict] = {}
    section: dict | None = None
    for raw in data.decode("latin-1").splitlines():
        line = re.split(r";|//", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        if match := SECTION.match(line):
            if len(result) >= MAX_SECTIONS:
                break
            section = result.setdefault(match[1].strip().upper(), {})
        elif section is not None and "=" in line and len(section) < MAX_KEYS:
            name, _, value = line.partition("=")
            section[name.strip().upper()[:60]] = _value(value)
    return result


def parse_lut(data: bytes) -> list[list[float]]:
    """[[x, y], ...] from lines like "5000|300". Long curves keep an even sample of the points."""
    points = []
    for raw in data.decode("latin-1").splitlines():
        line = re.split(r";|//", raw, maxsplit=1)[0].strip()
        parts = re.split(r"[|,]", line)
        if len(parts) == 2 and all(NUMBER.match(part.strip()) for part in parts):
            points.append([float(parts[0]), float(parts[1])])
    if len(points) > MAX_LUT_POINTS:
        last = len(points) - 1
        points = [points[round(i * last / (MAX_LUT_POINTS - 1))] for i in range(MAX_LUT_POINTS)]
    return [[round(x, 4), round(y, 4)] for x, y in points]


def parse_ratios(data: bytes) -> list[list]:
    """[[name, ratio], ...] from a .rto file ("name|ratio" lines, the name is a text)."""
    rows = []
    for raw in data.decode("latin-1").splitlines():
        parts = [part.strip() for part in raw.split("|")]
        if len(parts) == 2 and NUMBER.match(parts[1]):
            rows.append([parts[0][:40], float(parts[1])])
    return rows[:200]


def read_car_data(files: dict[str, bytes]) -> dict:
    """The data of a car from its files, by lower case name (from data.acd or a data folder)."""
    ini, lut, rto = {}, {}, {}
    for name, content in sorted(files.items()):
        stem, _, extension = name.rpartition(".")
        if stem in SKIPPED or not stem:
            continue
        if extension == "ini":
            if parsed := parse_ini(content):
                ini[stem] = parsed
        elif extension == "lut":
            if points := parse_lut(content):
                lut[stem] = points
        elif extension == "rto":
            if rows := parse_ratios(content):
                rto[stem] = rows
    return {"ini": ini, "lut": lut, **({"rto": rto} if rto else {})}


def tyre_compounds(data: dict) -> list[dict]:
    """The compounds of tyres.ini. A compound is [FRONT] and [REAR] for the first, then
    [FRONT_1] and [REAR_1], ... Each is a name, a short name, the size and the ideal pressure."""
    sections = data.get("ini", {}).get("tyres", {})
    compounds = []
    for index in range(0, 30):
        suffix = f"_{index}" if index else ""
        front = sections.get(f"FRONT{suffix}")
        rear = sections.get(f"REAR{suffix}")
        if front is None and rear is None:
            if index == 0:
                continue
            break
        front, rear = front or {}, rear or {}
        compounds.append(
            {
                "index": index,
                "name": str(front.get("NAME") or rear.get("NAME") or ""),
                "short_name": str(front.get("SHORT_NAME") or rear.get("SHORT_NAME") or ""),
                "front": _tyre_side(front),
                "rear": _tyre_side(rear),
            }
        )
    return compounds


def _tyre_side(section: dict) -> dict:
    """The size and pressures as numbers. Data saved before the parser read "0.2<tab>(note)" as a
    number still holds the text, so it is read again here."""
    side = {}
    for key in ("WIDTH", "RADIUS", "RIM_RADIUS", "PRESSURE_IDEAL", "PRESSURE_STATIC"):
        value = _value(str(section[key])) if key in section else None
        if isinstance(value, (int, float)):
            side[key.lower()] = value
    if "WEAR_CURVE" in section:
        side["wear_curve"] = str(section["WEAR_CURVE"])
    return side
