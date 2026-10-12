#!/usr/bin/env python3
"""Piston Cup Paddock driver collector.

Runs on the PC of a driver, next to Assetto Corsa. It reads the AC shared memory while the
driver is on track, makes one record for each lap, and sends the laps to the app.

- It is optional. Results and standings work without it.
- It only reads the shared memory. It changes nothing in AC.
- It keeps each lap in its own spool folder first, and sends it later if the app is down.
- The screen shows the recording status all the time.

Only the Python standard library. Python 3.11 or newer, on Windows (AC shared memory). Run:
    python driver_collector.py --config driver.ini
"""

from __future__ import annotations

import argparse
import configparser
import ctypes
import json
import logging
import mmap
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("driver_collector")

VERSION = "1.0.0"
AC_LIVE = 2
SESSION_TYPES = {0: "practice", 1: "qualifying", 2: "race"}


# AC shared memory. Wide text is 2 bytes for each character (Windows wchar_t).


def wide(size: int):
    return ctypes.c_uint16 * size


def text(value) -> str:
    return "".join(chr(c) for c in value).split("\x00", 1)[0]


class Physics(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packet_id", ctypes.c_int),
        ("gas", ctypes.c_float),
        ("brake", ctypes.c_float),
        ("fuel", ctypes.c_float),
        ("gear", ctypes.c_int),
        ("rpm", ctypes.c_int),
        ("steer", ctypes.c_float),
        ("speed_kmh", ctypes.c_float),
    ]


class Graphics(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packet_id", ctypes.c_int),
        ("status", ctypes.c_int),
        ("session", ctypes.c_int),
        ("current_time", wide(15)),
        ("last_time", wide(15)),
        ("best_time", wide(15)),
        ("split", wide(15)),
        ("completed_laps", ctypes.c_int),
        ("position", ctypes.c_int),
        ("i_current_time", ctypes.c_int),
        ("i_last_time", ctypes.c_int),
        ("i_best_time", ctypes.c_int),
        ("session_time_left", ctypes.c_float),
        ("distance_traveled", ctypes.c_float),
        ("is_in_pit", ctypes.c_int),
        ("current_sector_index", ctypes.c_int),
        ("last_sector_time", ctypes.c_int),
        ("number_of_laps", ctypes.c_int),
        ("tyre_compound", wide(33)),
        ("replay_time_multiplier", ctypes.c_float),
        ("normalized_car_position", ctypes.c_float),
    ]


class Static(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("sm_version", wide(15)),
        ("ac_version", wide(15)),
        ("number_of_sessions", ctypes.c_int),
        ("num_cars", ctypes.c_int),
        ("car_model", wide(33)),
        ("track", wide(33)),
        ("player_name", wide(33)),
    ]


class SharedMemory:
    """Reads the three AC pages. Windows makes the pages when AC runs."""

    def __init__(self):
        self.pages = {
            name: mmap.mmap(-1, ctypes.sizeof(kind), tagname)
            for name, kind, tagname in (
                ("physics", Physics, "Local\\acpmf_physics"),
                ("graphics", Graphics, "Local\\acpmf_graphics"),
                ("static", Static, "Local\\acpmf_static"),
            )
        }

    def read(self) -> tuple[Physics, Graphics, Static]:
        def page(name, kind):
            memory = self.pages[name]
            memory.seek(0)
            return kind.from_buffer_copy(memory.read(ctypes.sizeof(kind)))

        return page("physics", Physics), page("graphics", Graphics), page("static", Static)


# Lap recording. Pure logic, so the tests can feed samples without AC.


@dataclass
class Sample:
    live: bool
    session: int
    completed_laps: int
    lap_ms: int  # Time in the current lap.
    last_lap_ms: int
    pos: float
    speed_kmh: float
    gas: float
    brake: float
    steer: float
    gear: int
    rpm: int
    track: str
    car: str


@dataclass
class Recorder:
    hz: int
    channels: dict[str, list[float]] = field(default_factory=dict)
    lap_number: int | None = None
    status: str = "waiting"  # "waiting" (AC not on track) or "recording"

    def _reset(self) -> None:
        self.channels = {
            name: []
            for name in ("t_ms", "pos", "speed_kmh", "gas", "brake", "steer", "gear", "rpm")
        }

    def feed(self, sample: Sample) -> dict | None:
        """Add one sample. Gives a finished lap when the lap counter goes up."""
        if not sample.live:
            self.status = "waiting"
            return None
        self.status = "recording"
        finished = None
        if self.lap_number is None:
            self.lap_number = sample.completed_laps
            self._reset()
        elif sample.completed_laps != self.lap_number:
            # The first lap is from the pit or the grid. The lap after a session change is
            # not a real lap. Both still go to the app with their number.
            if sample.completed_laps == self.lap_number + 1 and len(self.channels["t_ms"]) > 1:
                finished = {
                    "track": sample.track,
                    "car": sample.car,
                    "session_type": SESSION_TYPES.get(sample.session, ""),
                    "lap_number": sample.completed_laps,
                    "lap_time_ms": sample.last_lap_ms,
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "sample_hz": self.hz,
                    "channels": self.channels,
                }
            self.lap_number = sample.completed_laps
            self._reset()
        values = {
            "t_ms": sample.lap_ms,
            "pos": round(sample.pos, 5),
            "speed_kmh": round(sample.speed_kmh, 1),
            "gas": round(sample.gas, 3),
            "brake": round(sample.brake, 3),
            "steer": round(sample.steer, 4),
            "gear": sample.gear,
            "rpm": sample.rpm,
        }
        for name, value in values.items():
            self.channels[name].append(value)
        return finished


def to_sample(physics: Physics, graphics: Graphics, static: Static) -> Sample:
    return Sample(
        live=graphics.status == AC_LIVE,
        session=graphics.session,
        completed_laps=graphics.completed_laps,
        lap_ms=graphics.i_current_time,
        last_lap_ms=graphics.i_last_time,
        pos=graphics.normalized_car_position,
        speed_kmh=physics.speed_kmh,
        gas=physics.gas,
        brake=physics.brake,
        steer=physics.steer,
        gear=physics.gear,
        rpm=physics.rpm,
        track=text(static.track),
        car=text(static.car_model),
    )


# Spool and upload


class Spool:
    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def add(self, lap: dict) -> Path:
        name = f"{int(time.time() * 1000)}-lap{lap['lap_number']}"
        temporary = self.folder / f"{name}.tmp"
        temporary.write_text(json.dumps(lap), encoding="utf-8")
        # The rename makes the full file appear at once, so the uploader never reads half.
        return temporary.replace(self.folder / f"{name}.json")

    def waiting(self) -> list[Path]:
        return sorted(self.folder.glob("*.json"))

    def done(self, path: Path) -> None:
        path.rename(path.with_suffix(".sent"))


def send(app_url: str, key: str, path: Path) -> dict:
    request = urllib.request.Request(
        app_url + "/api/telemetry/laps",
        data=path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": f"paddock-driver-collector/{VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def upload_waiting(app_url: str, key: str, spool: Spool) -> bool:
    for path in spool.waiting():
        try:
            send(app_url, key, path)
        except urllib.error.HTTPError as error:
            if error.code == 422:
                log.error("App refused %s. It stays in the spool as .refused.", path.name)
                path.rename(path.with_suffix(".refused"))
                continue
            log.warning("Upload failed: HTTP %s", error.code)
            return False
        except (urllib.error.URLError, OSError) as error:
            log.warning("Upload failed: %s", error)
            return False
        spool.done(path)
    return True


class Uploader(threading.Thread):
    """Sends the spool in the background, so a slow network never stops the recording."""

    def __init__(self, app_url: str, key: str, spool: Spool):
        super().__init__(daemon=True, name="upload")
        self.app_url, self.key, self.spool = app_url, key, spool
        self.wake = threading.Event()

    def run(self) -> None:
        while True:
            ok = upload_waiting(self.app_url, self.key, self.spool)
            self.wake.wait(30 if ok else 120)
            self.wake.clear()


def show_status(recorder: Recorder, spool: Spool) -> None:
    waiting = len(spool.waiting())
    if recorder.status == "recording":
        line = f"[REC] lap {(recorder.lap_number or 0) + 1} · {recorder.hz} Hz"
    else:
        line = "[--] waiting for AC on track"
    line += f" · {waiting} laps to send"
    sys.stdout.write("\r" + line.ljust(60))
    sys.stdout.flush()
    (spool.folder / "status.json").write_text(
        json.dumps({"status": recorder.status, "lap": recorder.lap_number, "to_send": waiting}),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=Path("driver.ini"))
    parser.add_argument("--check", action="store_true", help="Check the key and stop.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="\n%(asctime)s %(levelname)s %(message)s")
    config = configparser.ConfigParser()
    if not config.read(args.config, encoding="utf-8"):
        raise SystemExit(f"Cannot read {args.config}")
    app_url = config["app"]["url"].rstrip("/")
    key = config["app"]["key"].strip()
    hz = max(1, min(config.getint("collector", "sample_hz", fallback=20), 60))
    spool = Spool(Path(config.get("collector", "spool_dir", fallback="driver-spool")))

    if args.check:
        request = urllib.request.Request(
            app_url + "/api/telemetry/status", headers={"Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.loads(response.read()))
        return

    memory = SharedMemory()
    recorder = Recorder(hz)
    uploader = Uploader(app_url, key, spool)
    uploader.start()
    next_status = 0.0
    while True:
        started = time.monotonic()
        lap = recorder.feed(to_sample(*memory.read()))
        if lap:
            spool.add(lap)
            uploader.wake.set()  # Send the new lap soon.
        if started >= next_status:
            show_status(recorder, spool)
            next_status = started + 1
        time.sleep(max(0.0, 1 / hz - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
