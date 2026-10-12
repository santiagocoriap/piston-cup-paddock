"""Read an Assetto Corsa server result file. Pure functions with no database.

The field map is in docs/DATA_SOURCES.md. Important points from the real samples:
- Match drivers by the GUID in Laps[], not by the GUID in Result[]. They can differ.
- An entry with no laps did not take part. Skip it.
- Result[] is in classification order: laps first, then total time.
- DurationSecs is 0 for a timed race, and Cuts is always 0. Do not use them.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

SESSION_TYPES = {"PRACTICE": "practice", "QUALIFY": "qualifying", "RACE": "race"}
NO_LAP = 999999999


class ResultFileError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class ParsedLap:
    car_id: int
    guid: str
    lap_time_ms: int
    sectors_ms: list[int]
    cuts: int
    tyre: str
    ballast_kg: int
    restrictor: int
    timestamp_ms: int


@dataclass
class ParsedDriver:
    car_id: int
    guid: str
    name: str
    car_model: str
    laps: int
    total_time_ms: int
    best_lap_ms: int | None
    ballast_kg: int
    restrictor: int
    result_guid: str  # The GUID in Result[]. A warning shows when it differs.


@dataclass
class ParsedSession:
    track: str
    layout: str
    session_type: str
    drivers: list[ParsedDriver]  # In classification order.
    laps: list[ParsedLap]
    missing: list[str] = field(default_factory=list)


def track_key(raw: str) -> str:
    """Remove the CSP prefix: "csp/3460/../D/../ks_highlands" gives "ks_highlands"."""
    return raw.replace("\\", "/").rstrip("/").split("/")[-1]


def parse(data: dict) -> ParsedSession:
    if not isinstance(data, dict) or not {"Type", "Result", "Laps"} <= data.keys():
        raise ResultFileError("not_a_result_file")
    session_type = SESSION_TYPES.get(str(data.get("Type", "")).upper())
    if session_type is None:
        raise ResultFileError("unknown_session_type")

    laps = [
        ParsedLap(
            car_id=lap["CarId"],
            guid=str(lap.get("DriverGuid") or ""),
            lap_time_ms=lap["LapTime"],
            sectors_ms=list(lap.get("Sectors") or []),
            cuts=lap.get("Cuts", 0),
            tyre=str(lap.get("Tyre") or ""),
            ballast_kg=lap.get("BallastKG", 0),
            restrictor=lap.get("Restrictor", 0),
            timestamp_ms=lap.get("Timestamp", 0),
        )
        for lap in data.get("Laps") or []
    ]
    laps_by_car: dict[int, list[ParsedLap]] = {}
    for lap in laps:
        laps_by_car.setdefault(lap.car_id, []).append(lap)

    lap_names = {lap["CarId"]: lap.get("DriverName", "") for lap in data.get("Laps") or []}
    drivers = []
    for row in data.get("Result") or []:
        car_laps = laps_by_car.get(row["CarId"])
        if not car_laps:
            continue  # No lap: the driver did not take part.
        guid = Counter(lap.guid for lap in car_laps).most_common(1)[0][0]
        best = row.get("BestLap")
        drivers.append(
            ParsedDriver(
                car_id=row["CarId"],
                guid=guid,
                name=lap_names.get(row["CarId"]) or row.get("DriverName", ""),
                car_model=str(row.get("CarModel") or ""),
                laps=len(car_laps),
                total_time_ms=row.get("TotalTime", 0),
                best_lap_ms=best if best and best != NO_LAP else None,
                ballast_kg=row.get("BallastKG", 0),
                restrictor=row.get("Restrictor", 0),
                result_guid=str(row.get("DriverGuid") or ""),
            )
        )

    missing = ["conditions", "penalties", "cuts"]
    if not any(lap.sectors_ms for lap in laps):
        missing.append("sectors")
    if not data.get("Events"):
        missing.append("collisions")
    return ParsedSession(
        track=track_key(str(data.get("TrackName", ""))),
        layout=str(data.get("TrackConfig") or ""),
        session_type=session_type,
        drivers=drivers,
        laps=laps,
        missing=missing,
    )


_STEAM_GUID = re.compile(r"^\d{17}$")


def is_steam_guid(value: str) -> bool:
    return bool(_STEAM_GUID.match(value))
