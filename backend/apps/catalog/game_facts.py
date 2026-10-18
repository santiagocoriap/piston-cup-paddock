"""Read the facts of a track layout (ui_track.json) and a car (ui_car.json).

Mod authors write these files by hand, so the formats differ a lot. For example, the power of
a car can be "540bhp", "584 whp", "600+ bhp", or "--". Each reader takes the first number it
can trust and gives None for anything else. The car keeps the texts of "specs" as they are.
"""

import html
import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
MAX_TAGS = 30
MAX_CURVE_POINTS = 300


def _text(value, limit: int) -> str:
    return str(value).strip()[:limit] if isinstance(value, str | int | float) else ""


def _number(value) -> float | None:
    """The first number of a text. "1,030 kg" and "1.030 kg" are both 1030 when the part after
    the separator has 3 digits, else the separator is a decimal point."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str) or "nan" in value.lower():
        return None
    match = NUMBER.search(value)
    if not match:
        return None
    digits = match.group(0)
    head, _, tail = digits.replace(",", ".").partition(".")
    return float(head + tail) if len(tail) == 3 else float(digits.replace(",", "."))


def _whole(value, low: float, high: float) -> int | None:
    """A whole number inside a sane range, or None."""
    number = _number(value)
    return round(number) if number is not None and low <= number <= high else None


def _length(value) -> int | None:
    """Metres. Some tracks give kilometres ("5.2 km", "5,200 km"), most give metres ("12191")."""
    if isinstance(value, str) and "km" in value.lower():
        match = NUMBER.search(value)
        number = float(match.group(0).replace(",", ".")) if match else None
    else:
        number = _number(value)
    if number is None:
        return None
    metres = number * 1000 if "km" in str(value).lower() or number < 100 else number
    return round(metres) if 100 <= metres <= 100_000 else None


def _speed(value) -> int | None:
    """km/h. A text with "mp" or "mph" is in miles per hour."""
    number = _number(value)
    if number is None:
        return None
    text = str(value).lower()
    kmh = number * 1.609344 if "mp" in text and "km" not in text else number
    return round(kmh) if 20 <= kmh <= 1200 else None


def _year(value) -> int | None:
    return _whole(value, 1880, 2100)


def _tags(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [tag.strip()[:50] for tag in value if isinstance(tag, str) and tag.strip()][:MAX_TAGS]


def _description(value) -> str:
    """Plain text. The game files use <br> for a new line and sometimes other HTML tags."""
    text = _text(value, 10_000)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()[:5000]


def _direction(value) -> str:
    text = _text(value, 40).lower().replace("-", " ")
    if "anti" in text or "counter" in text:
        return "anticlockwise"
    if "clockwise" in text:
        return "clockwise"
    return ""


def _coordinate(value, limit: float) -> float | None:
    """A latitude or a longitude: "56.0353", "56.0353 N", or "3.5 W" (negative)."""
    number = _number(value)
    if number is None:
        return None
    text = str(value).upper()
    if ("S" in text or "W" in text) and not str(value).strip().startswith("-"):
        number = -number
    elif str(value).strip().startswith("-"):
        number = -number
    return number if -limit <= number <= limit else None


def _curve(value) -> list[list[float]]:
    """[[rpm, value], ...] with numbers only."""
    if not isinstance(value, list):
        return []
    points = []
    for point in value[:MAX_CURVE_POINTS]:
        if (
            isinstance(point, list)
            and len(point) == 2
            and all(isinstance(n, int | float) and not isinstance(n, bool) for n in point)
        ):
            points.append([float(point[0]), round(float(point[1]), 2)])
    return points


def _url(value) -> str:
    text = _text(value, 300)
    return text if text.lower().startswith(("http://", "https://")) else ""


def layout_facts(info: dict) -> dict:
    """The fields of a TrackLayout from ui_track.json. A missing value is None or empty."""
    geotags = info.get("geotags") if isinstance(info.get("geotags"), list) else []
    return {
        "length_m": _length(info.get("length")),
        "country": _text(info.get("country"), 100),
        "city": _text(info.get("city"), 100),
        "width_m": _whole(info.get("width"), 3, 100),
        "pit_boxes": _whole(info.get("pitboxes"), 1, 200),
        "direction": _direction(info.get("run")),
        "latitude": _coordinate(geotags[0], 90) if len(geotags) == 2 else None,
        "longitude": _coordinate(geotags[1], 180) if len(geotags) == 2 else None,
        "year": _year(info.get("year")),
        "author": _text(info.get("author"), 200),
        "version": _text(info.get("version"), 50),
        "url": _url(info.get("url")),
        "description": _description(info.get("description")),
        "tags": _tags(info.get("tags")),
    }


def car_facts(info: dict) -> dict:
    """The fields of a Car from ui_car.json. A missing value is None or empty."""
    specs = info.get("specs") if isinstance(info.get("specs"), dict) else {}
    return {
        "brand": _text(info.get("brand"), 100),
        "author": _text(info.get("author"), 200),
        "game_class": _text(info.get("class"), 60),
        "country": _text(info.get("country"), 100),
        "year": _year(info.get("year")),
        "power_hp": _whole(specs.get("bhp"), 10, 3000),
        "torque_nm": _whole(specs.get("torque"), 10, 5000),
        "weight_kg": _whole(specs.get("weight"), 30, 10_000),
        "top_speed_kmh": _speed(specs.get("topspeed")),
        "acceleration": _text(specs.get("acceleration"), 60)
        if _number(specs.get("acceleration"))
        else "",
        "power_to_weight": _text(specs.get("pwratio"), 60) if _number(specs.get("pwratio")) else "",
        "specs_text": {key: _text(value, 100) for key, value in specs.items() if _text(value, 100)},
        "version": _text(info.get("version"), 50),
        "url": _url(info.get("url")),
        "description": _description(info.get("description")),
        "tags": _tags(info.get("tags")),
        "power_curve": _curve(info.get("powerCurve")),
        "torque_curve": _curve(info.get("torqueCurve")),
    }


def data_facts(data: dict) -> dict:
    """Specs that ui_car.json left empty, worked out from the data folder (car.data). Weight is
    TOTALMASS, power the peak of power.lut (rpm, hp), torque the peak of hp * 7121 / rpm, and the
    top speed is the speed at the rev limiter in the top gear (the real one can be lower, as
    drag is not counted). A missing value is None."""
    ini = data.get("ini", {}) if isinstance(data, dict) else {}
    facts: dict = {"power_hp": None, "torque_nm": None, "weight_kg": None, "top_speed_kmh": None}
    facts["weight_kg"] = _whole(ini.get("car", {}).get("BASIC", {}).get("TOTALMASS"), 30, 10_000)
    points = [p for p in data.get("lut", {}).get("power", []) if p[0] > 500 and p[1] > 0]
    if points:
        facts["power_hp"] = _whole(max(p[1] for p in points), 10, 3000)
        facts["torque_nm"] = _whole(max(p[1] * 7121 / p[0] for p in points), 10, 5000)
    gears = ini.get("drivetrain", {}).get("GEARS", {})
    top = gears.get(f"GEAR_{gears.get('COUNT')}")
    final = gears.get("FINAL")
    limiter = ini.get("engine", {}).get("ENGINE_DATA", {}).get("LIMITER")
    radius = ini.get("tyres", {}).get("REAR", {}).get("RADIUS")
    numbers = (top, final, limiter, radius)
    if all(isinstance(n, int | float) and not isinstance(n, bool) and n > 0 for n in numbers):
        metres_per_second = limiter / 60 * 2 * 3.14159265 * radius / (top * final)
        facts["top_speed_kmh"] = _speed(round(metres_per_second * 3.6))
    return facts


def fill_empty(item, facts: dict) -> list[str]:
    """Copy each fact to a field that is still empty. An admin edit is never replaced.
    Returns the names of the fields that changed."""
    changed = []
    for name, value in facts.items():
        if value in (None, "", [], {}):
            continue
        if getattr(item, name) in (None, "", [], {}):
            setattr(item, name, value)
            changed.append(name)
    return changed
