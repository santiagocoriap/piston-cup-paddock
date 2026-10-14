#!/usr/bin/env python3
"""Piston Cup Paddock server collector.

Runs next to the Assetto Corsa server. It sends new result files, Real Penalty logs, and
(optionally) UDP plugin events to the app.

Safety rules:
- It only reads the server folders, with one exception: with write_server_config on, it writes
  the race setup that an admin sends from the app ("Enviar al servidor") into the Content
  Manager preset. It writes only while the AC server is stopped, it keeps a copy of the old
  files first, and it changes only its own keys. It never starts or stops the server.
- It sends one packet to the AC server only when request_positions is on: the request for
  car positions (REALTIMEPOS_INTERVAL). It never sends any other command.
- It keeps a copy of each file and each event in its own spool folder first. An app outage
  only delays the upload. The game server never waits for the collector.
- It accepts UDP packets only from this computer (127.0.0.1 or ::1).

Only the Python standard library. Python 3.11 or newer. Run:
    python paddock_collector.py --config collector.ini
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import json
import logging
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("paddock_collector")

VERSION = "1.0.0"
EVENT_BATCH = 200
PING_SECONDS = 300  # The app shows a collector as stopped after 15 minutes without a ping.
LOCAL_ADDRESSES = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

# AC server UDP plugin protocol (from the Kunos SDK example).
NEW_SESSION = 50
NEW_CONNECTION = 51
CONNECTION_CLOSED = 52
CAR_UPDATE = 53
END_SESSION = 55
CLIENT_LOADED = 58
LAP_COMPLETED = 73
CLIENT_EVENT = 130
CE_COLLISION_WITH_CAR = 10
CE_COLLISION_WITH_ENV = 11
REALTIMEPOS_INTERVAL = 200
POSITION_CHUNK_SECONDS = 5


# Settings


@dataclass
class Settings:
    app_url: str
    key: str
    results_dir: Path | None
    penalty_dir: Path | None
    spool_dir: Path
    udp_port: int = 0
    server_udp_port: int = 0  # UDP_PLUGIN_LOCAL_PORT of server_cfg.ini.
    request_positions: bool = False
    position_interval_ms: int = 200
    result_stable_seconds: int = 10
    log_stable_seconds: int = 600
    poll_seconds: int = 15
    since: str = ""  # Files older than this date (YYYY-MM-DD) are not sent.
    # The server_cfg.ini that the AC server uses. The collector reads the time of day and the
    # start grip from it at each new session. Empty: the app gets no time of day and no grip.
    server_cfg: Path | None = None
    # The Content Manager preset folder of the league server, for "Enviar al servidor".
    preset_dir: Path | None = None
    # Off by default: the collector only reads. The server owner turns it on.
    write_server_config: bool = False
    # Free slots after the league drivers, so a driver can change to an extra car.
    open_slots: int = 10

    @classmethod
    def load(cls, path: Path) -> Settings:
        parser = configparser.ConfigParser()
        if not parser.read(path, encoding="utf-8"):
            raise SystemExit(f"Cannot read {path}")
        app, server, collector = parser["app"], parser["server"], parser["collector"]

        def folder(value: str) -> Path | None:
            return Path(value) if value.strip() else None

        return cls(
            app_url=app["url"].rstrip("/"),
            key=app["key"].strip(),
            results_dir=folder(server.get("results_dir", "")),
            server_cfg=folder(server.get("server_cfg", ""))
            or (
                Path(server["preset_dir"]) / "server_cfg.ini"
                if server.get("preset_dir", "").strip()
                else None
            ),
            preset_dir=folder(server.get("preset_dir", "")),
            write_server_config=collector.getboolean("write_server_config", False),
            open_slots=max(0, collector.getint("open_slots", 10)),
            penalty_dir=folder(server.get("realpenalty_logs_dir", "")),
            spool_dir=Path(collector.get("spool_dir", "spool")),
            udp_port=collector.getint("udp_port", 0),
            server_udp_port=collector.getint("server_udp_port", 0),
            request_positions=collector.getboolean("request_positions", False),
            position_interval_ms=max(100, collector.getint("position_interval_ms", 200)),
            result_stable_seconds=collector.getint("result_stable_seconds", 10),
            log_stable_seconds=collector.getint("log_stable_seconds", 600),
            poll_seconds=collector.getint("poll_seconds", 15),
            since=collector.get("since", "").strip(),
        )


# Local state


class State:
    """A small SQLite file in the spool folder. Each thread opens its own connection."""

    def __init__(self, path: Path):
        self.path = path
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS files (
                    sha256 TEXT PRIMARY KEY, name TEXT, kind TEXT, spooled TEXT,
                    sent_at TEXT, status TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT, seq INTEGER, body TEXT, sent INTEGER DEFAULT 0,
                    PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def meta(self, name: str, default: str = "") -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
        return row[0] if row else default

    def set_meta(self, name: str, value: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (name, value))

    def known(self, sha256: str) -> bool:
        with self._connect() as db:
            return (
                db.execute("SELECT 1 FROM files WHERE sha256 = ?", (sha256,)).fetchone() is not None
            )

    def add_file(self, sha256: str, name: str, kind: str, spooled: Path) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO files (sha256, name, kind, spooled) VALUES (?, ?, ?, ?)",
                (sha256, name, kind, str(spooled)),
            )

    def unsent_files(self) -> list[tuple[str, str, str, str]]:
        with self._connect() as db:
            return db.execute(
                "SELECT sha256, name, kind, spooled FROM files WHERE sent_at IS NULL"
            ).fetchall()

    def mark_file(self, sha256: str, status: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE files SET sent_at = ?, status = ? WHERE sha256 = ?",
                (now_iso(), status, sha256),
            )

    def add_event(self, run_id: str, seq: int, body: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO events (run_id, seq, body) VALUES (?, ?, ?)",
                (run_id, seq, json.dumps(body)),
            )

    def unsent_events(self, limit: int) -> list[tuple[str, int, str]]:
        with self._connect() as db:
            return db.execute(
                "SELECT run_id, seq, body FROM events WHERE sent = 0 ORDER BY run_id, seq LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_events(self, run_id: str, seqs: list[int]) -> None:
        with self._connect() as db:
            db.executemany(
                "UPDATE events SET sent = 1 WHERE run_id = ? AND seq = ?",
                [(run_id, seq) for seq in seqs],
            )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Files


def stable(path: Path, seconds: int, now: float) -> bool:
    """True when the file did not change for the given time."""
    return now - path.stat().st_mtime >= seconds


def candidates(settings: Settings, now: float) -> list[tuple[Path, str]]:
    """The finished files of the server folders. A Real Penalty log counts as finished when
    a newer log exists, or when it did not change for log_stable_seconds."""
    since = 0.0
    if settings.since:
        since = datetime.strptime(settings.since, "%Y-%m-%d").timestamp()
    found: list[tuple[Path, str]] = []
    if settings.results_dir and settings.results_dir.is_dir():
        for path in settings.results_dir.glob("*.json"):
            if path.stat().st_mtime >= since and stable(path, settings.result_stable_seconds, now):
                found.append((path, "result"))
    if settings.penalty_dir and settings.penalty_dir.is_dir():
        logs = sorted(settings.penalty_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        for index, path in enumerate(logs):
            if path.stat().st_mtime < since:
                continue
            newer_exists = index < len(logs) - 1
            if newer_exists or stable(path, settings.log_stable_seconds, now):
                found.append((path, "penalty_log"))
    return found


def spool_files(settings: Settings, state: State, now: float) -> int:
    """Copy each new finished file to the spool folder. The upload reads the copy."""
    added = 0
    folder = settings.spool_dir / "files"
    folder.mkdir(parents=True, exist_ok=True)
    for path, kind in candidates(settings, now):
        try:
            content = path.read_bytes()
        except OSError as error:  # The server can hold the file for a moment.
            log.warning("Cannot read %s: %s", path, error)
            continue
        sha256 = hashlib.sha256(content).hexdigest()
        if state.known(sha256):
            continue
        copy = folder / f"{sha256[:16]}-{path.name}"
        copy.write_bytes(content)
        state.add_file(sha256, path.name, kind, copy)
        log.info("New %s: %s", kind, path.name)
        added += 1
    return added


# Upload


class App:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _request(self, path: str, body: bytes, content_type: str) -> dict:
        request = urllib.request.Request(
            self.settings.app_url + path,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.key}",
                "Content-Type": content_type,
                "User-Agent": f"paddock-collector/{VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")

    def send_file(self, name: str, kind: str, content: bytes) -> dict:
        boundary = uuid.uuid4().hex
        body = io.BytesIO()
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="kind"\r\n\r\n'.encode())
        body.write(f"{kind}\r\n".encode())
        body.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
        )
        body.write(content)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        return self._request(
            "/api/collector/files", body.getvalue(), f"multipart/form-data; boundary={boundary}"
        )

    def ping(self) -> None:
        """Tell the app that the collector runs, also when there is nothing to send."""
        request = urllib.request.Request(
            self.settings.app_url + "/api/collector/ping",
            headers={
                "Authorization": f"Bearer {self.settings.key}",
                "User-Agent": f"paddock-collector/{VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()

    def send_events(self, run_id: str, events: list[dict]) -> dict:
        body = json.dumps({"run_id": run_id, "events": events}).encode()
        return self._request("/api/collector/events", body, "application/json")

    def get_command(self) -> dict:
        request = urllib.request.Request(
            self.settings.app_url + "/api/collector/commands",
            headers={
                "Authorization": f"Bearer {self.settings.key}",
                "User-Agent": f"paddock-collector/{VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")

    def report(self, push_id: int, status: str, error: str = "") -> dict:
        body = json.dumps({"status": status, "error": error}).encode()
        return self._request(f"/api/collector/commands/{push_id}", body, "application/json")


# Race setup ("Enviar al servidor")

PADDOCK_SCRIPT = "/api/script/paddock.lua"
# A car, track, layout, or weather name: a folder name of AC.
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]*$")
STEAM_ID = re.compile(r"^\d{17}$")


def ini_value(value) -> str:
    """A value for one ini line. A line break or a control character could add a new line,
    for example a new admin password, so they become spaces."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()


def safe_name(value) -> str:
    text = str(value or "")
    if not SAFE_NAME.match(text):
        raise ValueError(f"unsafe_name:{text[:40]!r}")
    return text


def read_text(path: Path) -> tuple[str, str]:
    """The text of an ini file and its line end. Content Manager can write CRLF."""
    if not path.exists():
        return "", "\r\n"
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), newline


def write_text(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def ini_split(text: str) -> list[tuple[str | None, list[str]]]:
    """The sections of an ini text, in order, with their lines. The first part has no name."""
    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            parts.append((stripped[1 : stripped.index("]")], [line]))
        else:
            parts[-1][1].append(line)
    return parts


def ini_join(parts: list[tuple[str | None, list[str]]]) -> str:
    return "\n".join(line for _, lines in parts for line in lines)


def ini_get(text: str, section: str, key: str) -> str | None:
    for name, lines in ini_split(text):
        if name is not None and name.upper() == section.upper():
            for line in lines[1:]:
                left, _, right = line.partition("=")
                if right and left.strip().upper() == key.upper():
                    # A comment starts with a space and ";". CARS uses ";" with no space.
                    return re.split(r"\s+;", right)[0].strip()
    return None


def ini_set(text: str, section: str, key: str, value) -> str:
    """Set one key and keep every other line. Adds the key or the section when it is missing."""
    parts = ini_split(text)
    for name, lines in parts:
        if name is not None and name.upper() == section.upper():
            for index, line in enumerate(lines[1:], start=1):
                left, sep, _ = line.partition("=")
                if sep and left.strip().upper() == key.upper():
                    lines[index] = f"{left.rstrip()}={ini_value(value)}"
                    return ini_join(parts)
            # Before the empty lines at the end of the section.
            end = len(lines)
            while end > 1 and not lines[end - 1].strip():
                end -= 1
            lines.insert(end, f"{key}={ini_value(value)}")
            return ini_join(parts)
    body = ini_join(parts).rstrip("\n")
    return f"{body}\n\n[{section}]\n{key}={ini_value(value)}\n"


def car_blocks(text: str) -> list[dict[str, str]]:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # Keep the case of the keys.
    parser.read_string(text or "")
    return [
        dict(parser[name])
        for name in sorted(
            (n for n in parser.sections() if n.upper().startswith("CAR_")),
            key=lambda n: int(n.split("_")[1]) if n.split("_")[1].isdigit() else 999,
        )
    ]


def car_skins(content_dir: Path, model: str) -> list[str]:
    skins = content_dir / "cars" / model / "skins"
    if not skins.is_dir():
        return []
    return sorted(child.name for child in skins.iterdir() if child.is_dir())


def first_skin(content_dir: Path, model: str) -> str:
    names = car_skins(content_dir, model)
    return names[0] if names else ""


def entry_list(
    old_text: str, entries: list[dict], content_dir: Path, open_slots: int = 10
) -> tuple[str, list[str]]:
    """The new entry list: one car for each league driver, then the open slots (the league
    cars in turn, so a driver can change car), then the spectator slots of the preset (for
    example Race Control). Gives the text and the car models."""
    old = car_blocks(old_text)
    skins: dict[str, str] = {}
    for block in old:
        model = block.get("MODEL", "").lower()
        if model and block.get("SKIN") and model not in skins:
            skins[model] = block["SKIN"]
    cars = []
    for entry in entries:
        model = safe_name(entry["model"])
        guid = str(entry.get("guid") or "")
        cars.append(
            {
                "DRIVERNAME": ini_value(entry["name"]),
                "TEAM": ini_value(entry.get("team", "")),
                "GUID": guid if STEAM_ID.match(guid) else "",
                "MODEL": model,
                "SKIN": skins.get(model.lower()) or first_skin(content_dir, model),
                "BALLAST": str(int(entry.get("ballast_kg", 0))),
                "SPECTATOR_MODE": "0",
                "RESTRICTOR": str(int(entry.get("restrictor_pct", 0))),
            }
        )
    league_models = list(dict.fromkeys(car["MODEL"] for car in cars))
    used = {(car["MODEL"].lower(), car["SKIN"]) for car in cars}
    for index in range(open_slots if league_models else 0):
        model = league_models[index % len(league_models)]
        # A skin that no other car uses yet, when the server has one.
        choices = car_skins(content_dir, model) or [skins.get(model.lower(), "")]
        free = [skin for skin in choices if (model.lower(), skin) not in used]
        skin = (free or choices)[0]
        used.add((model.lower(), skin))
        cars.append(
            {
                "DRIVERNAME": "",
                "TEAM": "",
                "GUID": "",
                "MODEL": model,
                "SKIN": skin,
                "BALLAST": "0",
                "SPECTATOR_MODE": "0",
                "RESTRICTOR": "0",
            }
        )
    cars += [block for block in old if block.get("SPECTATOR_MODE", "0").strip() == "1"]
    lines = []
    for index, car in enumerate(cars):
        lines.append(f"[CAR_{index}]")
        lines += [f"{key}={ini_value(value)}" for key, value in car.items()]
        lines.append("")
    models = list(dict.fromkeys(car["MODEL"] for car in cars if car.get("MODEL")))
    return "\n".join(lines), models


def server_settings(text: str, content: dict, models: list[str], cars: int) -> str:
    """The new server_cfg.ini: the track, the cars, and the conditions. Other lines stay."""
    track = content["track"]
    old_track = ini_get(text, "SERVER", "TRACK") or ""
    # Keep a prefix such as "csp/3460/../": it tells AC that the server needs CSP.
    prefix = old_track[: old_track.rfind("/") + 1] if old_track.startswith("csp/") else ""
    text = ini_set(text, "SERVER", "TRACK", prefix + safe_name(track["key"]))
    text = ini_set(text, "SERVER", "CONFIG_TRACK", safe_name(track.get("layout", "")))
    text = ini_set(text, "SERVER", "CARS", ";".join(models))
    try:
        clients = int(ini_get(text, "SERVER", "MAX_CLIENTS") or 0)
    except ValueError:
        clients = 0
    text = ini_set(text, "SERVER", "MAX_CLIENTS", max(clients, cars))
    wanted = content.get("conditions") or {}
    if "sun_angle" in wanted:
        text = ini_set(text, "SERVER", "SUN_ANGLE", int(wanted["sun_angle"]))
    if "grip_pct" in wanted:
        text = ini_set(text, "DYNAMIC_TRACK", "SESSION_START", int(wanted["grip_pct"]))
    parts = ini_split(text)
    if "weather" in wanted:
        # One weather only: the announced one.
        parts = [
            part
            for part in parts
            if part[0] is None
            or not part[0].upper().startswith("WEATHER_")
            or part[0].upper() == "WEATHER_0"
        ]
        text = ini_set(ini_join(parts), "WEATHER_0", "GRAPHICS", safe_name(wanted["weather"]))
        parts = ini_split(text)
    weathers = [name for name, _ in parts if name and name.upper().startswith("WEATHER_")] or [
        "WEATHER_0"
    ]
    for name in weathers:
        if "air_temp_c" in wanted:
            text = ini_set(text, name, "BASE_TEMPERATURE_AMBIENT", int(wanted["air_temp_c"]))
        if "road_offset_c" in wanted:
            text = ini_set(text, name, "BASE_TEMPERATURE_ROAD", int(wanted["road_offset_c"]))
    return text


def _quoted(value) -> str:
    """A CSP option value in quotes. A quote in the value cannot close it early."""
    return "'" + ini_value(value).replace("'", "") + "'"


def csp_options(text: str, script: dict) -> str:
    """The CSP options with the Paddock script section. The other sections stay."""
    parts = ini_split(text)
    used = []
    for name, lines in parts:
        if name and name.upper().startswith("SCRIPT_"):
            used.append(name)
            if any(PADDOCK_SCRIPT in line for line in lines):
                text = ini_set(text, name, "SCRIPT", _quoted(script["url"]))
                return ini_set(text, name, "raceCode", _quoted(script["race_code"]))
    numbers = {int(n.split("_")[1]) for n in used if n.split("_")[1].isdigit()}
    section = f"SCRIPT_{max(numbers, default=0) + 1}"
    text = ini_set(text, section, "SCRIPT", _quoted(script["url"]))
    return ini_set(text, section, "raceCode", _quoted(script["race_code"]))


def server_running(preset_dir: Path) -> bool:
    """True when an AC server runs on this PC, or the TCP port of the preset is in use."""
    try:
        listed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq acServer.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if "acserver.exe" in listed.stdout.lower():
            return True
    except (OSError, subprocess.SubprocessError):
        pass  # Not Windows: the port check below still works.
    text, _ = read_text(preset_dir / "server_cfg.ini")
    try:
        port = int(ini_get(text, "SERVER", "TCP_PORT") or 0)
    except ValueError:
        port = 0
    if port:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return True
        finally:
            probe.close()
    return False


def write_setup(
    preset_dir: Path, content: dict, now: datetime | None = None, open_slots: int = 10
) -> Path:
    """Write the race setup into the preset. Gives the folder with the copy of the old files."""
    now = now or datetime.now()
    backup = preset_dir / "paddock-backups" / now.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=True)
    names = ("server_cfg.ini", "entry_list.ini", "csp_extra_options.ini")
    for name in names:
        if (preset_dir / name).exists():
            shutil.copy2(preset_dir / name, backup / name)
    content_dir = preset_dir.parent.parent / "content"
    entries_old, entries_newline = read_text(preset_dir / "entry_list.ini")
    entries_text, models = entry_list(entries_old, content["entries"], content_dir, open_slots)
    cfg_old, cfg_newline = read_text(preset_dir / "server_cfg.ini")
    cfg_text = server_settings(cfg_old, content, models, len(car_blocks(entries_text)))
    csp_old, csp_newline = read_text(preset_dir / "csp_extra_options.ini")
    csp_text = csp_options(csp_old, content["script"])
    write_text(preset_dir / "entry_list.ini", entries_text, entries_newline)
    write_text(preset_dir / "server_cfg.ini", cfg_text, cfg_newline)
    write_text(preset_dir / "csp_extra_options.ini", csp_text, csp_newline)
    return backup


def handle_command(app: App, settings: Settings, reported: dict[int, str]) -> None:
    """Do the push that waits, if any. A step goes to the app one time only."""
    command = app.get_command()
    push_id, content = command.get("id"), command.get("content")
    if not push_id or not content:
        return

    def tell(status: str, error: str = "") -> None:
        if reported.get(push_id) != status:
            app.report(push_id, status, error)
            reported[push_id] = status

    if not settings.write_server_config or settings.preset_dir is None:
        tell("failed", "writing_disabled")
        return
    if server_running(settings.preset_dir):
        tell("waiting", "server_running")
        return
    try:
        backup = write_setup(settings.preset_dir, content, open_slots=settings.open_slots)
    except (OSError, ValueError, KeyError, configparser.Error) as error:
        log.exception("Writing the race setup failed")
        tell("failed", type(error).__name__)
        return
    log.info(
        "Wrote the race setup of round %s. Copy of the old files: %s",
        content["round"]["number"],
        backup,
    )
    tell("done")


def upload_pending(app: App, state: State) -> bool:
    """Send what is waiting. Gives False after a failure, so the caller waits longer."""
    for sha256, name, kind, spooled in state.unsent_files():
        try:
            result = app.send_file(name, kind, Path(spooled).read_bytes())
        except urllib.error.HTTPError as error:
            if 400 <= error.code < 500 and error.code not in (401, 403, 408, 429):
                # The app refuses this file. Sending it again does not help.
                log.error("App refused %s: HTTP %s", name, error.code)
                state.mark_file(sha256, f"refused_{error.code}")
                continue
            log.warning("Upload of %s failed: HTTP %s", name, error.code)
            return False
        except (urllib.error.URLError, OSError) as error:
            log.warning("Upload of %s failed: %s", name, error)
            return False
        state.mark_file(sha256, result.get("status", "sent"))
        log.info("Sent %s: %s", name, result.get("status"))
    while rows := state.unsent_events(EVENT_BATCH):
        run_id = rows[0][0]
        batch = [(seq, body) for row_run, seq, body in rows if row_run == run_id]
        events = [{**json.loads(body), "seq": seq} for seq, body in batch]
        try:
            app.send_events(run_id, events)
        except (urllib.error.URLError, OSError) as error:
            log.warning("Event upload failed: %s", error)
            return False
        state.mark_events(run_id, [seq for seq, _ in batch])
    return True


# UDP plugin events


class Reader:
    """Little-endian reader for the AC UDP plugin packets."""

    def __init__(self, data: bytes):
        self.buf = io.BytesIO(data)

    def _unpack(self, fmt: str, size: int):
        raw = self.buf.read(size)
        if len(raw) != size:
            raise struct.error("short packet")
        return struct.unpack(fmt, raw)[0]

    def byte(self) -> int:
        return self._unpack("<B", 1)

    def uint16(self) -> int:
        return self._unpack("<H", 2)

    def uint32(self) -> int:
        return self._unpack("<I", 4)

    def int32(self) -> int:
        return self._unpack("<i", 4)

    def single(self) -> float:
        return self._unpack("<f", 4)

    def vec3(self) -> tuple[float, float, float]:
        return self.single(), self.single(), self.single()

    def string(self) -> str:
        return self.buf.read(self.byte()).decode("ascii", errors="replace")

    def stringw(self) -> str:
        return self.buf.read(self.byte() * 4).decode("utf-32-le", errors="replace")


def time_of_day(sun_angle: float) -> str:
    """The clock time of an AC sun angle: 0 is 13:00, and 16 degrees is one hour."""
    minutes = round(13 * 60 + sun_angle * 60 / 16)
    minutes = max(0, min(24 * 60 - 1, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def server_conditions(path: Path | None) -> dict:
    """The time of day and the start grip from server_cfg.ini. The collector only reads it."""
    if path is None:
        return {}
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        if not parser.read(path, encoding="utf-8"):
            return {}
    except (configparser.Error, UnicodeDecodeError):
        return {}
    found: dict = {}
    try:
        found["time_of_day"] = time_of_day(float(parser.get("SERVER", "SUN_ANGLE")))
    except (configparser.Error, ValueError):
        pass
    try:
        found["grip_pct"] = int(parser.get("DYNAMIC_TRACK", "SESSION_START"))
    except (configparser.Error, ValueError):
        pass
    return found


def parse_packet(data: bytes, drivers: dict[int, dict]) -> dict | None:
    """One UDP packet to one event, or None for a packet that the app does not use.
    drivers maps car IDs to the driver, so events can carry the GUID."""
    reader = Reader(data)
    packet = reader.byte()

    def car(car_id: int) -> dict:
        return {"car_id": car_id, **drivers.get(car_id, {})}

    if packet == NEW_SESSION:
        reader.byte()  # protocol version
        reader.byte()  # session index
        reader.byte()  # current session index
        reader.byte()  # session count
        reader.stringw()  # server name
        track = reader.string()
        layout = reader.string()
        name = reader.string()
        kind = reader.byte()
        minutes = reader.uint16()
        laps = reader.uint16()
        data = {
            "track": track,
            "layout": layout,
            "name": name,
            "type": kind,
            "minutes": minutes,
            "laps": laps,
        }
        try:
            # The conditions of the session. An old server can send a shorter packet.
            reader.uint16()  # wait time
            data["air_temp_c"] = reader.byte()
            data["road_temp_c"] = reader.byte()
            data["weather"] = reader.string()
        except struct.error:
            pass
        return {"kind": "session_started", "data": data}
    if packet in (NEW_CONNECTION, CONNECTION_CLOSED):
        name = reader.stringw()
        guid = reader.stringw()
        car_id = reader.byte()
        model = reader.string()
        if packet == NEW_CONNECTION:
            drivers[car_id] = {"guid": guid, "name": name, "car_model": model}
        else:
            drivers.pop(car_id, None)
        kind = "connected" if packet == NEW_CONNECTION else "disconnected"
        return {
            "kind": kind,
            "data": {"car_id": car_id, "guid": guid, "name": name, "car_model": model},
        }
    if packet == LAP_COMPLETED:
        car_id = reader.byte()
        lap_ms = reader.uint32()
        cuts = reader.byte()
        return {"kind": "lap_completed", "data": {**car(car_id), "lap_ms": lap_ms, "cuts": cuts}}
    if packet == CLIENT_EVENT:
        event = reader.byte()
        car_id = reader.byte()
        other = reader.byte() if event == CE_COLLISION_WITH_CAR else None
        speed = reader.single()
        x, y, z = reader.vec3()
        data = {**car(car_id), "speed_kmh": round(speed, 1), "x": x, "y": y, "z": z}
        if event == CE_COLLISION_WITH_CAR:
            data["other"] = car(other) if other is not None else None
            return {"kind": "collision_car", "data": data}
        if event == CE_COLLISION_WITH_ENV:
            return {"kind": "collision_env", "data": data}
        return None
    if packet == CAR_UPDATE:
        car_id = reader.byte()
        x, _y, z = reader.vec3()
        reader.vec3()  # velocity
        reader.byte()  # gear
        reader.uint16()  # rpm
        spline = reader.single()
        return {"kind": "car_update", "data": {"car_id": car_id, "x": x, "z": z, "n": spline}}
    if packet == END_SESSION:
        return {"kind": "session_ended", "data": {"result_file": reader.stringw()}}
    if packet == CLIENT_LOADED:
        return {"kind": "client_loaded", "data": car(reader.byte())}
    return None


class EventListener(threading.Thread):
    """Listens as a Content Manager extra plugin. With request_positions on, it asks the
    server for car positions at each new session. It sends nothing else."""

    def __init__(self, settings: Settings, state: State, run_id: str):
        super().__init__(daemon=True, name="udp")
        self.settings = settings
        self.state = state
        self.run_id = run_id
        self.seq = 0
        self.drivers: dict[int, dict] = {}
        self.sock: socket.socket | None = None
        # Positions come many times a second. They go to the app in chunks of 5 seconds.
        self.chunk_start: float | None = None
        self.chunk: dict[str, list[list[float]]] = {}

    def _store(self, event: dict) -> None:
        self.state.add_event(self.run_id, self.seq, event)
        self.seq += 1

    def flush_positions(self) -> dict | None:
        if self.chunk_start is None or not self.chunk:
            return None
        event = {
            "kind": "positions",
            "at": datetime.fromtimestamp(self.chunk_start, UTC).isoformat(),
            "data": {"cars": self.chunk},
        }
        self._store(event)
        self.chunk_start, self.chunk = None, {}
        return event

    def add_position(self, data: dict, now: float) -> None:
        if self.chunk_start is not None and now - self.chunk_start >= POSITION_CHUNK_SECONDS:
            self.flush_positions()
        if self.chunk_start is None:
            self.chunk_start = now
        driver = self.drivers.get(data["car_id"], {})
        key = driver.get("guid") or f"car:{data['car_id']}"
        offset_ms = round((now - self.chunk_start) * 1000)
        self.chunk.setdefault(key, []).append(
            [offset_ms, round(data["x"], 1), round(data["z"], 1), round(data["n"], 4)]
        )

    def request_positions(self) -> None:
        settings = self.settings
        if not (settings.request_positions and settings.server_udp_port and self.sock):
            return
        packet = struct.pack("<BH", REALTIMEPOS_INTERVAL, settings.position_interval_ms)
        self.sock.sendto(packet, ("127.0.0.1", settings.server_udp_port))
        log.info("Asked the server for positions every %s ms", settings.position_interval_ms)

    def handle(self, data: bytes, source: str, now: float | None = None) -> dict | None:
        if source not in LOCAL_ADDRESSES:
            log.warning("Ignored a UDP packet from %s", source)
            return None
        try:
            event = parse_packet(data, self.drivers)
        except (struct.error, IndexError, UnicodeDecodeError):
            return None  # A short or broken packet must not stop the listener.
        if event is None:
            return None
        now = time.time() if now is None else now
        if event["kind"] == "car_update":
            self.add_position(event["data"], now)
            return event
        if event["kind"] in ("session_started", "session_ended"):
            self.flush_positions()
        if event["kind"] == "session_started":
            event["data"].update(server_conditions(self.settings.server_cfg))
        event["at"] = datetime.fromtimestamp(now, UTC).isoformat()
        self._store(event)
        if event["kind"] == "session_started":
            self.request_positions()
        return event

    def run(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", self.settings.udp_port))
        self.sock.settimeout(1.0)
        log.info("Listening for UDP plugin events on 127.0.0.1:%s", self.settings.udp_port)
        self.request_positions()  # A session can already run when the collector starts.
        while True:
            try:
                data, (source, _port) = self.sock.recvfrom(4096)
            except TimeoutError:
                if self.chunk_start and time.time() - self.chunk_start >= POSITION_CHUNK_SECONDS:
                    self.flush_positions()
                continue
            except OSError:
                continue  # Windows can report a closed remote port here. It is harmless.
            self.handle(data, source)


# Main loop


def run(settings: Settings) -> None:
    settings.spool_dir.mkdir(parents=True, exist_ok=True)
    state = State(settings.spool_dir / "state.sqlite3")
    if not settings.since:
        # The first start only sends files from today on. Old races stay out.
        settings.since = state.meta("since") or datetime.now().strftime("%Y-%m-%d")
        state.set_meta("since", settings.since)
    app = App(settings)
    if settings.udp_port:
        EventListener(settings, state, uuid.uuid4().hex).start()
    wait = settings.poll_seconds
    next_ping = 0.0
    reported: dict[int, str] = {}
    while True:
        try:
            spool_files(settings, state, time.time())
            ok = upload_pending(app, state)
            handle_command(app, settings, reported)
            if time.time() >= next_ping:
                app.ping()
                next_ping = time.time() + PING_SECONDS
        except Exception:  # The loop must keep running. The log has the details.
            log.exception("Collector loop error")
            ok = False
        # After a failure, wait longer each time, up to 10 minutes.
        wait = settings.poll_seconds if ok else min(wait * 2, 600)
        time.sleep(wait)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=Path("collector.ini"))
    parser.add_argument("--check", action="store_true", help="Check the key and stop.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.load(args.config)
    if args.check:
        request = urllib.request.Request(
            settings.app_url + "/api/collector/ping",
            headers={"Authorization": f"Bearer {settings.key}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.loads(response.read()))
        return
    run(settings)


if __name__ == "__main__":
    main()
