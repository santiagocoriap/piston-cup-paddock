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

The Windows program (paddock-collector.exe, built by GitHub Actions) also has:
    --install     show the setup window, then put the shortcut "Iniciar Paddock" on the desktop
    --setup       show the setup window only (the folders of the AC server)
    --uninstall   remove the shortcut
While it runs, an icon next to the Windows clock shows the state. Its menu has "Configurar…",
"Abrir registro", and "Salir".
The admin uses the shortcut before a race, in place of Real Penalty: the collector starts Real
Penalty (realpenalty_exe in collector.ini) and itself. The collector stops by itself after the AC
server stops. It never starts with Windows. At each start, it asks the app for a new version.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import hashlib
import io
import json
import logging
import logging.handlers
import os
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("paddock_collector")

VERSION = "1.7.0"
UPDATE_SECONDS = 24 * 3600
SHORTCUT_NAME = "Iniciar Paddock.lnk"
# Only one collector runs on a PC: the second one cannot take this local port, and it stops.
INSTANCE_PORT = 47615
# Without an AC server, the collector stops after this time. A forgotten collector stops too.
NO_SERVER_SECONDS = 6 * 3600
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
    # Free slots after the league drivers, when the app sends no number (an old app).
    open_slots: int = 10
    # ac_penalty.exe. The collector starts it, when it does not run yet. Empty: not started.
    realpenalty_exe: Path | None = None
    # The collector stops this many minutes after the AC server stops. 0: it never stops.
    stop_after_minutes: int = 15
    # collector.ini. A push to another preset saves the new preset there.
    config_path: Path | None = None

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
            realpenalty_exe=folder(server.get("realpenalty_exe", "")),
            stop_after_minutes=max(0, collector.getint("stop_after_minutes", 15)),
            config_path=path,
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
        # Real Penalty writes two series at the same time: output_<time>.log and
        # practice_penalty_<time>.log (also qualify_ and race_). A log is finished when a newer
        # log of the same series exists. A log of the other series says nothing about it.
        series: dict[str, list[Path]] = {}
        for path in settings.penalty_dir.glob("*.log"):
            series.setdefault(log_series(path.name), []).append(path)
        for logs in series.values():
            logs.sort(key=lambda p: p.name)  # The name ends with the start time.
            for index, path in enumerate(logs):
                if path.stat().st_mtime < since:
                    continue
                newer_exists = index < len(logs) - 1
                if newer_exists or stable(path, settings.log_stable_seconds, now):
                    found.append((path, "penalty_log"))
    return found


def log_series(name: str) -> str:
    """ "practice_penalty_20261014_205243.log" -> "practice_penalty"."""
    return re.sub(r"_?\d[\d_]*\.log$", "", name, flags=re.IGNORECASE) or name


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

    def send_status(self, status: dict) -> dict:
        body = json.dumps(status).encode()
        return self._request("/api/collector/status", body, "application/json")

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

    def _get(self, path: str, timeout: int = 30) -> bytes:
        request = urllib.request.Request(
            self.settings.app_url + path,
            headers={
                "Authorization": f"Bearer {self.settings.key}",
                "User-Agent": f"paddock-collector/{VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def get_version(self) -> dict:
        return json.loads(self._get("/api/collector/version") or b"{}")

    def download_program(self) -> bytes:
        return self._get("/api/collector/download", timeout=300)


# Update (the Windows program only)


def newer(version: str, than: str) -> bool:
    def parts(text: str) -> tuple[int, ...]:
        return tuple(int(n) for n in re.findall(r"\d+", text)[:3])

    return parts(version) > parts(than)


def program_path() -> Path | None:
    """The .exe of the Windows program. None when Python runs the script: no self-update."""
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def apply_update(exe: Path, data: bytes, sha256: str) -> None:
    """Put the new program in the place of the old one. Windows lets a running program file
    get a new name, so the old file becomes <name>.old.exe. The next start deletes it."""
    if hashlib.sha256(data).hexdigest() != sha256.lower():
        raise ValueError("The new program has a wrong SHA-256 sum")
    new = exe.with_name(f"{exe.stem}.new.exe")
    old = exe.with_name(f"{exe.stem}.old.exe")
    new.write_bytes(data)
    old.unlink(missing_ok=True)
    exe.replace(old)
    new.replace(exe)


def remove_old_program(exe: Path | None) -> None:
    if exe is None:
        return
    try:
        exe.with_name(f"{exe.stem}.old.exe").unlink(missing_ok=True)
    except OSError:
        pass  # The old program still stops. The next start tries again.


def check_update(app: App, exe: Path | None) -> bool:
    """True when a new program is in place. The caller then starts it."""
    if exe is None:
        return False
    found = app.get_version()
    version, sha256 = found.get("version"), found.get("sha256")
    if not version or not sha256 or not newer(version, VERSION):
        return False
    log.info("Updating the collector from %s to %s", VERSION, version)
    apply_update(exe, app.download_program(), sha256)
    return True


def restart(exe: Path) -> None:
    # PYINSTALLER_RESET_ENVIRONMENT: the new program unpacks its own files, not the files of
    # this program, which go away when this program stops.
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    release_instance()  # The new program must get the port of the single collector.
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen([str(exe), *sys.argv[1:]], env=env, creationflags=flags, close_fds=True)
    logging.shutdown()
    os._exit(0)


# The icon next to the Windows clock: the state, and a menu to set up, read the log, or stop.

STOP = threading.Event()  # "Salir": the main loop stops at once.
AGAIN = threading.Event()  # After "Configurar…": the collector starts again with the new folders.
STATUS = {"text": "Paddock: arrancando"}

MENU_SETUP, MENU_LOG, MENU_EXIT = 1, 2, 3


def set_status(text: str) -> None:
    STATUS["text"] = f"Paddock: {text}"[:127]


def own_command(*arguments: str) -> list[str]:
    """This program with other arguments: the .exe, or Python with this script."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    return [sys.executable, str(Path(__file__).resolve()), *arguments]


def tray_action(command: int, config: Path, run_setup=None, open_file=None) -> None:
    """What a menu item does. run_setup and open_file are for the tests."""
    if command == MENU_SETUP:
        run_setup = run_setup or (
            lambda: subprocess.run(own_command("--setup", "--config", str(config)), check=False)
        )
        if run_setup().returncode == 0:
            log.info("New setup saved. The collector starts again.")
            AGAIN.set()
            STOP.set()
    elif command == MENU_LOG:
        (open_file or os.startfile)(str(config.parent / "collector.log"))
    elif command == MENU_EXIT:
        log.info("Stopped from the icon.")
        STOP.set()


class Tray(threading.Thread):
    """The tray icon, with the Windows API through ctypes (no extra package)."""

    def __init__(self, config: Path):
        super().__init__(daemon=True, name="tray")
        self.config = config

    def run(self) -> None:
        try:
            self._loop()
        except Exception:  # Without the icon, the collector still works.
            log.exception("Tray icon error")

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        lresult = ctypes.c_ssize_t
        wndproc = ctypes.WINFUNCTYPE(
            lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class NotifyIconData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON),
            ]

        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = lresult
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.LPVOID,
        ]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_size_t,
            wintypes.LPCWSTR,
        ]
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user32.LoadIconW.restype = wintypes.HICON
        shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
        shell32.ExtractIconW.restype = wintypes.HICON
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NotifyIconData)]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

        wm_destroy, wm_timer, wm_tray = 0x0002, 0x0113, 0x0400 + 20
        wm_lbuttonup, wm_rbuttonup = 0x0202, 0x0205
        nim_add, nim_modify, nim_delete = 0, 1, 2
        nif_message, nif_icon, nif_tip = 1, 2, 4

        instance = kernel32.GetModuleHandleW(None)
        icon = shell32.ExtractIconW(instance, sys.executable, 0) if program_path() else None
        icon = icon or user32.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))
        data = NotifyIconData()
        shown = {"tip": ""}

        def update_tip(hwnd) -> None:
            if STATUS["text"] != shown["tip"]:
                shown["tip"] = data.szTip = STATUS["text"]
                shell32.Shell_NotifyIconW(nim_modify, ctypes.byref(data))

        def show_menu(hwnd) -> None:
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, 0x0001, 0, f"Paddock colector {VERSION}")  # Grayed.
            user32.AppendMenuW(menu, 0x0800, 0, None)  # A line.
            user32.AppendMenuW(menu, 0, MENU_SETUP, "Configurar…")
            user32.AppendMenuW(menu, 0, MENU_LOG, "Abrir registro")
            user32.AppendMenuW(menu, 0x0800, 0, None)
            user32.AppendMenuW(menu, 0, MENU_EXIT, "Salir")
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)  # Else the menu does not close on a click outside.
            command = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, hwnd, None)
            user32.DestroyMenu(menu)
            if command:
                threading.Thread(
                    target=tray_action, args=(command, self.config), daemon=True
                ).start()

        def proc(hwnd, message, wparam, lparam):
            if message == wm_tray and lparam in (wm_lbuttonup, wm_rbuttonup):
                show_menu(hwnd)
                return 0
            if message == wm_timer:
                if STOP.is_set():
                    user32.DestroyWindow(hwnd)
                else:
                    update_tip(hwnd)
                return 0
            if message == wm_destroy:
                shell32.Shell_NotifyIconW(nim_delete, ctypes.byref(data))
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._proc = wndproc(proc)  # Keep a reference: Windows calls it.
        window_class = WndClass(
            lpfnWndProc=self._proc, hInstance=instance, lpszClassName="PaddockTray"
        )
        user32.RegisterClassW(ctypes.byref(window_class))
        hwnd = user32.CreateWindowExW(
            0, "PaddockTray", "Paddock", 0, 0, 0, 0, 0, None, None, instance, None
        )
        data.cbSize = ctypes.sizeof(NotifyIconData)
        data.hWnd = hwnd
        data.uID = 1
        data.uFlags = nif_message | nif_icon | nif_tip
        data.uCallbackMessage = wm_tray
        data.hIcon = icon
        data.szTip = shown["tip"] = STATUS["text"]
        if not shell32.Shell_NotifyIconW(nim_add, ctypes.byref(data)):
            log.warning("Windows did not show the tray icon")
            return
        log.info("Tray icon shown")
        user32.SetTimer(hwnd, 1, 1000, None)
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


def start_again() -> None:
    """Start this program again, for example after a new setup."""
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(own_command(*sys.argv[1:]), env=env, creationflags=flags, close_fds=True)


# Start and stop with the race (Real Penalty, the desktop shortcut, and the stop)


# The Windows program has no console. Without this flag, each tasklist or PowerShell call opens
# a console window for a moment.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def process_running(image: str) -> bool:
    """True when a program with this file name runs on this PC (Windows only)."""
    try:
        listed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return image.lower() in listed.stdout.lower()


def start_real_penalty(settings: Settings) -> bool:
    """Start Real Penalty in its own window, as the admin did by hand. True when started."""
    exe = settings.realpenalty_exe
    if exe is None or process_running(exe.name):
        return False
    if not exe.is_file():
        log.warning("Real Penalty is not at %s", exe)
        return False
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen([str(exe)], cwd=exe.parent, creationflags=flags, close_fds=True)
    log.info("Started Real Penalty: %s", exe)
    return True


class Lifetime:
    """When the collector stops by itself: some time after the AC server stops, when nothing
    waits for the upload. The wait is longer than the wait for the last Real Penalty log."""

    def __init__(self, settings: Settings, now: float):
        minutes = settings.stop_after_minutes
        self.wait = max(minutes * 60, settings.log_stable_seconds + 300) if minutes else 0
        self.seen = False  # The admin starts the collector before the server.
        self.last = now

    def done(self, server_up: bool, idle: bool, now: float) -> bool:
        if not self.wait:
            return False
        if server_up:
            self.seen, self.last = True, now
            return False
        limit = self.wait if self.seen else NO_SERVER_SECONDS
        return idle and now - self.last >= limit


def ac_server_up(settings: Settings) -> bool:
    if settings.preset_dir:
        return server_running(settings.preset_dir)
    return process_running("acServer.exe")


_holder: list[socket.socket] = []


def one_instance(port: int = INSTANCE_PORT) -> bool:
    """Hold a local port that only one collector can hold. False: a collector already runs."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", port))
    except OSError:
        holder.close()
        return False
    _holder.append(holder)
    return True


def release_instance() -> None:
    while _holder:
        _holder.pop().close()


def say(text: str) -> None:
    """A message for the admin. The Windows program has no console, so it shows a window."""
    log.info(text)
    if sys.stdout is not None:
        print(text)
    elif os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Paddock", 0x40)


def launch(config: Path) -> tuple[str, str]:
    """The program and the arguments of the shortcut."""
    if getattr(sys, "frozen", False):
        target, first = sys.executable, []
    else:
        target, first = sys.executable, [str(Path(__file__).resolve())]
    return target, subprocess.list2cmdline([*first, "--config", str(config.resolve())])


# PowerShell gets the values in environment variables, so a path cannot change the script.
MAKE_SHORTCUT = (
    "$d=[Environment]::GetFolderPath('Desktop');"
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d $env:PADDOCK_NAME));"
    "$s.TargetPath=$env:PADDOCK_TARGET;$s.Arguments=$env:PADDOCK_ARGS;"
    "$s.WorkingDirectory=$env:PADDOCK_DIR;"
    "$s.Description='Real Penalty y el colector de Paddock';$s.Save()"
)
REMOVE_SHORTCUT = (
    "$d=[Environment]::GetFolderPath('Desktop');"
    "Remove-Item -LiteralPath (Join-Path $d $env:PADDOCK_NAME) -ErrorAction SilentlyContinue"
)


def _powershell(script: str, values: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "PADDOCK_NAME": SHORTCUT_NAME, **values},
        capture_output=True,
        text=True,
        check=False,
        creationflags=NO_WINDOW,
    )


def load_settings(config: Path) -> Settings | None:
    """The settings, or None after a message for the admin. The Windows program has no
    console, so an error with no message looks like a program that does nothing."""
    try:
        return Settings.load(config)
    except (SystemExit, configparser.Error, KeyError, ValueError) as error:
        say(f"collector.ini tiene un error: {error}")
        return None


# Setup window: the admin picks the folders. Nobody edits collector.ini by hand.

SETUP_FIELDS = ("results_dir", "realpenalty_exe", "realpenalty_logs_dir", "preset_dir")


def steam_libraries(steam_root: Path | None = None) -> list[Path]:
    """The Steam library folders of this PC, from the registry and libraryfolders.vdf."""
    roots: list[Path] = []
    if steam_root is not None:
        roots.append(steam_root)
    elif os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        roots.append(Path(r"C:\Program Files (x86)\Steam"))
    found: list[Path] = []
    for root in roots:
        found.append(root)
        text, _ = read_text(root / "steamapps" / "libraryfolders.vdf")
        found += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    unique: list[Path] = []
    for path in found:
        if str(path).lower() not in {str(u).lower() for u in unique}:
            unique.append(path)
    return unique


def find_ac(libraries: list[Path]) -> Path | None:
    for library in libraries:
        ac = library / "steamapps" / "common" / "assettocorsa"
        if (ac / "server").is_dir():
            return ac
    return None


def presets(ac: Path) -> list[Path]:
    """The Content Manager presets of the server. A preset with CSP options (a league preset)
    comes first, then the last changed one."""
    return presets_in(ac / "server" / "presets")


def presets_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir() if (p / "server_cfg.ini").is_file()]

    def rank(preset: Path) -> tuple[bool, float]:
        csp = (preset / "csp_extra_options.ini").is_file()
        return csp, (preset / "server_cfg.ini").stat().st_mtime

    return sorted(found, key=rank, reverse=True)


def preset_name(preset: Path) -> str:
    """The name that Content Manager shows: NAME of server_cfg.ini, without the " x:..." id that
    Content Manager adds. The folder name when there is no NAME."""
    text, _ = read_text(preset / "server_cfg.ini")
    name = re.sub(r"\s+x:\S+$", "", (ini_get(text, "SERVER", "NAME") or "").strip())
    return name or preset.name


def preset_labels(found: list[Path]) -> dict[str, Path]:
    """The names for a list. Two presets with the same name also show their folder."""
    names = [preset_name(p) for p in found]
    return {
        (name if names.count(name) == 1 else f"{name} ({preset.name})"): preset
        for name, preset in zip(names, found, strict=True)
    }


def preset_label(preset: Path) -> str:
    """The name of one preset in the list of its folder."""
    for label, path in preset_labels(presets(preset.parent.parent.parent)).items():
        if path == preset:
            return label
    return preset_name(preset)


def detect(ac: Path) -> dict[str, str]:
    """The folders and files of the collector in an Assetto Corsa folder. "" when not found."""
    server = ac / "server"
    realpenalty = server / "realpenalty"
    found_presets = presets(ac)
    return {
        "results_dir": str(server / "results") if (server / "results").is_dir() else "",
        "realpenalty_exe": (
            str(realpenalty / "ac_penalty.exe")
            if (realpenalty / "ac_penalty.exe").is_file()
            else ""
        ),
        "realpenalty_logs_dir": (
            str(realpenalty / "logs") if (realpenalty / "logs").is_dir() else ""
        ),
        "preset_dir": str(found_presets[0]) if found_presets else "",
    }


def initial_values(current: dict[str, str], found: dict[str, str]) -> dict[str, str]:
    """A saved path that exists stays. An empty path, or an example path that does not exist on
    this PC, takes the path that the collector found."""
    return {
        key: value if value and Path(value).exists() else found.get(key, "")
        for key, value in {k: current.get(k, "") for k in SETUP_FIELDS}.items()
    }


def setup_problems(values: dict[str, str]) -> list[str]:
    """What is wrong with the chosen folders. The results folder is necessary."""
    problems = []
    if not values.get("results_dir") or not Path(values["results_dir"]).is_dir():
        problems.append("Falta la carpeta de resultados del servidor.")
    exe = values.get("realpenalty_exe", "")
    if exe and not Path(exe).is_file():
        problems.append("El archivo de Real Penalty no existe.")
    logs = values.get("realpenalty_logs_dir", "")
    if logs and not Path(logs).is_dir():
        problems.append("La carpeta de logs de Real Penalty no existe.")
    preset = values.get("preset_dir", "")
    if preset and not (Path(preset) / "server_cfg.ini").is_file():
        problems.append("La carpeta del preset no tiene server_cfg.ini.")
    return problems


# The UDP ports between Real Penalty and the collector. Real Penalty gets the server events on
# the UDP plugin port of the server, and it sends a copy to the collector (RELAY_EVENTS). The
# collector sends its request for car positions to Real Penalty (RELAY_COMMANDS), which sends it
# to the server.
RELAY_EVENTS = 12000
RELAY_COMMANDS = 12001


def _list_add(text: str, item: str) -> str:
    items = [part.strip() for part in text.split(";") if part.strip()]
    return ";".join(items if item in items else [*items, item])


def relay_through_real_penalty(realpenalty_exe: Path) -> Path | None:
    """Add the collector to [Plugins_Relay] of the Real Penalty settings.ini. Gives the file,
    or None without one. The first change keeps a copy as settings.ini.paddock-backup."""
    path = realpenalty_exe.parent / "settings.ini"
    if not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        text, encoding = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        text, encoding = raw.decode("latin-1"), "latin-1"
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    address = f"127.0.0.1:{RELAY_EVENTS}"
    plugins = ini_get(text, "Plugins_Relay", "OTHER_UDP_PLUGIN") or ""
    if address in plugins:
        return path  # Already there. The two lists stay in the same order.
    ports = ini_get(text, "Plugins_Relay", "UDP_PORT") or ""
    text = ini_set(text, "Plugins_Relay", "OTHER_UDP_PLUGIN", _list_add(plugins, address))
    text = ini_set(text, "Plugins_Relay", "UDP_PORT", _list_add(ports, str(RELAY_COMMANDS)))
    backup = path.with_name("settings.ini.paddock-backup")
    if not backup.exists():
        backup.write_bytes(raw)
    path.write_bytes(text.replace("\n", newline).encode(encoding))
    return path


def app_problems(app: dict[str, str]) -> list[str]:
    problems = []
    if not re.match(r"^https?://[^\s]+$", app.get("url", "")):
        problems.append("La dirección de la app tiene que empezar con http:// o https://.")
    if not re.match(r"^pcc_[A-Za-z0-9_\-]{20,}$", app.get("key", "")):
        problems.append("La clave del colector empieza con pcc_. Copiala de la app.")
    return problems


def save_setup(
    config: Path,
    values: dict[str, str],
    write_server: bool,
    udp_relay: bool = False,
    app: dict[str, str] | None = None,
) -> None:
    """Write the chosen folders into collector.ini and keep every other line. udp_relay: get the
    server events through Real Penalty. app: a new app address and key."""
    text, newline = read_text(config)
    for key, value in (app or {}).items():
        text = ini_set(text, "app", key, value)
    for key in SETUP_FIELDS:
        text = ini_set(text, "server", key, values.get(key, ""))
    if values.get("preset_dir"):
        text = ini_set(text, "server", "server_cfg", "")  # The preset has its server_cfg.ini.
    text = ini_set(text, "collector", "write_server_config", "true" if write_server else "false")
    exe = values.get("realpenalty_exe", "")
    if udp_relay and exe and relay_through_real_penalty(Path(exe)):
        text = ini_set(text, "collector", "udp_port", RELAY_EVENTS)
        text = ini_set(text, "collector", "server_udp_port", RELAY_COMMANDS)
        text = ini_set(text, "collector", "request_positions", "true")
    write_text(config, text, newline)


def needs_setup(config: Path) -> bool:
    try:
        settings = Settings.load(config)
    except (SystemExit, configparser.Error, KeyError, ValueError):
        return True
    return settings.results_dir is None or not settings.results_dir.is_dir()


def setup_window(config: Path) -> bool:
    """The setup window. True when the admin saved."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    text, _ = read_text(config)
    current = {key: ini_get(text, "server", key) or "" for key in SETUP_FIELDS}
    ac = find_ac(steam_libraries())
    if ac:
        current = initial_values(current, detect(ac))
    write_now = (ini_get(text, "collector", "write_server_config") or "").lower() == "true"

    root = tk.Tk()
    root.title("Paddock: configurar el colector")
    root.resizable(True, False)
    # The app and the key. A new key from the app goes here: no new download.
    top = ttk.Frame(root, padding=(16, 16, 16, 0))
    top.grid(row=0, column=0, sticky="nsew")
    top.columnconfigure(1, weight=1)
    url_var = tk.StringVar(value=ini_get(text, "app", "url") or "")
    key_var = tk.StringVar(value=ini_get(text, "app", "key") or "")
    ttk.Label(top, text="Dirección de la app").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(top, textvariable=url_var, width=84).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Label(top, text="Clave del colector").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(top, textvariable=key_var, width=84, show="•").grid(
        row=1, column=1, sticky="ew", padx=8
    )
    ttk.Label(
        top,
        text=(
            "Para cambiar la clave: en la app, Colectores > Crear clave > Copiar clave. "
            "Pegala acá."
        ),
        foreground="#666",
    ).grid(row=2, column=1, sticky="w", padx=8)
    frame = ttk.Frame(root, padding=16)
    frame.grid(row=1, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    ttk.Label(
        frame,
        text=(
            "Elegí las carpetas del servidor de Assetto Corsa. "
            "Con la carpeta de Assetto Corsa, el colector busca el resto."
        ),
        wraplength=760,
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

    ac_var = tk.StringVar(value=str(ac) if ac else "")
    variables = {key: tk.StringVar(value=current.get(key, "")) for key in SETUP_FIELDS}
    labels = {
        "results_dir": "Resultados del servidor",
        "realpenalty_exe": "Real Penalty (ac_penalty.exe)",
        "realpenalty_logs_dir": "Logs de Real Penalty",
        "preset_dir": "Preset de Content Manager",
    }

    def fill_from_ac() -> None:
        folder = Path(ac_var.get())
        if (folder / "server").is_dir():
            for key, value in detect(folder).items():
                variables[key].set(value)
            show_presets(folder)

    def pick_ac() -> None:
        chosen = filedialog.askdirectory(title="Carpeta de Assetto Corsa", parent=root)
        if chosen:
            ac_var.set(str(Path(chosen)))
            fill_from_ac()

    def picker(key: str):
        def pick() -> None:
            if key == "realpenalty_exe":
                chosen = filedialog.askopenfilename(
                    title=labels[key], parent=root, filetypes=[("ac_penalty.exe", "*.exe")]
                )
            else:
                chosen = filedialog.askdirectory(title=labels[key], parent=root)
            if chosen:
                variables[key].set(str(Path(chosen)))
                if key == "preset_dir":
                    preset_text.set(preset_label(Path(chosen)))

        return pick

    ttk.Label(frame, text="Carpeta de Assetto Corsa").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=ac_var, width=84).grid(row=1, column=1, sticky="ew", padx=8)
    ttk.Button(frame, text="Buscar…", command=pick_ac).grid(row=1, column=2)
    ttk.Separator(frame).grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)

    # The list shows the names of Content Manager. The saved value is the folder.
    by_label: dict[str, Path] = {}
    preset_text = tk.StringVar()
    preset_box = ttk.Combobox(frame, textvariable=preset_text, width=82, state="readonly")

    def show_presets(folder: Path) -> None:
        by_label.clear()
        by_label.update(preset_labels(presets(folder)))
        preset_box["values"] = list(by_label)
        chosen = variables["preset_dir"].get()
        preset_text.set(preset_label(Path(chosen)) if chosen else "")

    def preset_chosen(_event=None) -> None:
        variables["preset_dir"].set(str(by_label[preset_text.get()]))

    preset_box.bind("<<ComboboxSelected>>", preset_chosen)
    if ac:
        show_presets(ac)
    for row, key in enumerate(SETUP_FIELDS, start=3):
        ttk.Label(frame, text=labels[key]).grid(row=row, column=0, sticky="w", pady=4)
        if key == "preset_dir":
            preset_box.grid(row=row, column=1, sticky="ew", padx=8)
        else:
            ttk.Entry(frame, textvariable=variables[key], width=84).grid(
                row=row, column=1, sticky="ew", padx=8
            )
        ttk.Button(frame, text="Buscar…", command=picker(key)).grid(row=row, column=2)

    # On by default: without the server events, the laps of the Paddock script cannot match.
    relay_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        frame,
        text=(
            "Recibir los datos en vivo del servidor a través de Real Penalty "
            "(vueltas, salidas de pista, posiciones)"
        ),
        variable=relay_var,
    ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))
    write_var = tk.BooleanVar(value=write_now)
    ttk.Checkbutton(
        frame,
        text='Permitir "Enviar al servidor": escribe el preset, solo con el servidor apagado',
        variable=write_var,
    ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))

    saved = {"done": False}

    def save() -> None:
        values = {key: variables[key].get().strip() for key in SETUP_FIELDS}
        app = {"url": url_var.get().strip(), "key": key_var.get().strip()}
        problems = app_problems(app) + setup_problems(values)
        if problems:
            messagebox.showerror("Paddock", "\n".join(problems), parent=root)
            return
        save_setup(config, values, write_var.get(), relay_var.get(), app)
        saved["done"] = True
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=9, column=0, columnspan=3, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Cancelar", command=root.destroy).grid(row=0, column=0, padx=8)
    ttk.Button(buttons, text="Guardar", command=save).grid(row=0, column=1)
    root.mainloop()
    return saved["done"]


def install(config: Path) -> int:
    if not setup_window(config):
        say("No se guardó nada. Abrí instalar.bat otra vez para configurar el colector.")
        return 1
    settings = load_settings(config)
    if settings is None:
        return 1
    target, arguments = launch(config)
    result = _powershell(
        MAKE_SHORTCUT,
        {"PADDOCK_TARGET": target, "PADDOCK_ARGS": arguments, "PADDOCK_DIR": str(config.parent)},
    )
    if result.returncode:
        say(f"No se pudo crear el acceso directo: {(result.stderr or result.stdout).strip()}")
        return 1
    text = (
        'Listo. En el escritorio está "Iniciar Paddock". Usalo antes de cada carrera, en lugar de '
        "abrir Real Penalty: abre Real Penalty y el colector. El colector se cierra solo cuando "
        "el servidor se apaga."
    )
    if settings.realpenalty_exe is None:
        text += " collector.ini no tiene realpenalty_exe, así que solo abre el colector."
    say(text)
    return 0


def uninstall() -> int:
    _powershell(REMOVE_SHORTCUT, {})
    say('Listo. El acceso directo "Iniciar Paddock" ya no está en el escritorio.')
    return 0


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
    if process_running("acServer.exe"):
        return True  # Not Windows: the port check below still works.
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
    names = ("server_cfg.ini", "entry_list.ini", "csp_extra_options.ini", "cm_welcome.txt")
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
    welcome_old, welcome_newline = read_text(preset_dir / "cm_welcome.txt")
    # The copy has the bytes of the file, with its line ends.
    welcome_text = welcome_with_csp(welcome_old, csp_text.replace("\n", csp_newline))
    write_text(preset_dir / "cm_welcome.txt", welcome_text, welcome_newline)
    return backup


CSP_BLOCK = re.compile(r"\t*\$CSP0:[A-Za-z0-9+/=]*")


def welcome_with_csp(welcome: str, csp_text: str) -> str:
    """The welcome text of the preset with a new copy of the CSP options. Content Manager does
    not read csp_extra_options.ini when it starts a server: it sends the copy that it keeps at
    the end of cm_welcome.txt, made when an admin saved the preset. The copy is 32 tabs, then
    $CSP0: and the options file, compressed with zlib, in base64 without "=". The tabs hide it
    in the chat of the players."""
    visible = CSP_BLOCK.sub("", welcome).rstrip()
    packed = base64.b64encode(zlib.compress(csp_text.rstrip("\r\n").encode("utf-8"), 9))
    return visible + "\t" * 32 + "$CSP0:" + packed.decode("ascii").rstrip("=")


CONTENT_MANAGER = ("Content Manager.exe", "Content Manager Safe.exe")


def content_manager_open() -> bool:
    return any(process_running(name) for name in CONTENT_MANAGER)


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
    target = chosen_preset(settings.preset_dir, content.get("preset"))
    if target is None:
        tell("failed", "unknown_preset")
        return
    if server_running(target):
        tell("waiting", "server_running")
        return
    if content_manager_open():
        # Content Manager keeps the preset in its memory, and it saves that copy over the files
        # when it starts the server. It reads the files again only when it opens.
        tell("waiting", "content_manager_open")
        return
    try:
        # The admin sets the free slots in the app. An old app sends no number.
        slots = content.get("open_slots", settings.open_slots)
        backup = write_setup(target, content, open_slots=int(slots))
    except (OSError, ValueError, KeyError, configparser.Error) as error:
        log.exception("Writing the race setup failed")
        tell("failed", type(error).__name__)
        return
    log.info(
        "Wrote the race setup of round %s into %s. Copy of the old files: %s",
        content["round"]["number"],
        target.name,
        backup,
    )
    if target != settings.preset_dir:
        use_preset(settings, target)
    tell("done")


def preset_list(settings: Settings) -> list[dict]:
    """The presets next to the preset of collector.ini, for the list in the app."""
    if settings.preset_dir is None:
        return []
    found = presets_in(settings.preset_dir.parent)
    return [{"folder": p.name, "name": label} for label, p in preset_labels(found).items()]


def chosen_preset(current: Path, folder: str | None) -> Path | None:
    """The preset of a push. Only a preset folder next to the preset of collector.ini: a name
    from the app cannot point to another folder."""
    if not folder:
        return current
    for preset in presets_in(current.parent):
        if preset.name == folder:
            return preset
    return None


def use_preset(settings: Settings, preset: Path) -> None:
    """The admin chose another preset in the app. It stays the preset for the next starts."""
    old_cfg = settings.preset_dir / "server_cfg.ini" if settings.preset_dir else None
    settings.preset_dir = preset
    if settings.server_cfg is None or settings.server_cfg == old_cfg:
        settings.server_cfg = preset / "server_cfg.ini"
    if settings.config_path and settings.config_path.exists():
        text, newline = read_text(settings.config_path)
        write_text(settings.config_path, ini_set(text, "server", "preset_dir", preset), newline)
    log.info("The preset is now %s", preset)


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
    next_ping = next_update = 0.0
    reported: dict[int, str] = {}
    exe = program_path()
    remove_old_program(exe)
    lifetime = Lifetime(settings, time.time())
    while True:
        try:
            spool_files(settings, state, time.time())
            ok = upload_pending(app, state)
            handle_command(app, settings, reported)
            if time.time() >= next_ping:
                app.ping()
                send_status(app, settings, state)
                next_ping = time.time() + PING_SECONDS
        except Exception:  # The loop must keep running. The log has the details.
            log.exception("Collector loop error")
            ok = False
        if exe and time.time() >= next_update:
            next_update = time.time() + UPDATE_SECONDS
            try:
                if check_update(app, exe):
                    restart(exe)
            except Exception:  # A failed update keeps the old program. It tries the next day.
                log.exception("Update error")
        idle = ok and not state.unsent_files() and not state.unsent_events(1)
        server_up = ac_server_up(settings)
        if lifetime.done(server_up, idle, time.time()):
            log.info("The AC server stopped and everything is sent. The collector stops.")
            return
        if not ok:
            set_status("sin conexión con la app, reintenta solo")
        elif server_up:
            set_status("servidor en marcha, mandando datos")
        else:
            set_status("esperando el servidor")
        # After a failure, wait longer each time, up to 10 minutes. "Salir" ends the wait.
        wait = settings.poll_seconds if ok else min(wait * 2, 600)
        if STOP.wait(wait):
            return


class LastError(logging.Handler):
    """Keeps the last warning or error, for the health page of the app."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.text = ""
        self.at: datetime | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self.text = record.getMessage().splitlines()[0][:200]
        self.at = datetime.fromtimestamp(record.created, UTC)


LAST_ERROR = LastError()


def status_body(settings: Settings, state: State) -> dict:
    body: dict = {
        "queued_files": len(state.unsent_files()),
        "last_error": LAST_ERROR.text,
        "last_error_at": LAST_ERROR.at.isoformat() if LAST_ERROR.at else None,
    }
    if settings.preset_dir is not None:
        body["presets"] = preset_list(settings)
        body["current"] = settings.preset_dir.name
    return body


def send_status(app: App, settings: Settings, state: State) -> None:
    app.send_status(status_body(settings, state))


def setup_logging(folder: Path) -> None:
    """The log goes to collector.log next to collector.ini (1 MB, with 3 older files), and to
    the console when there is one."""
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            folder / "collector.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
    ]
    handlers.append(LAST_ERROR)
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=Path("collector.ini"))
    parser.add_argument("--check", action="store_true", help="Check the key and stop.")
    parser.add_argument("--install", action="store_true", help="Make the desktop shortcut.")
    parser.add_argument("--uninstall", action="store_true", help="Remove the desktop shortcut.")
    parser.add_argument("--setup", action="store_true", help="Show the setup window.")
    args = parser.parse_args()
    config = args.config.resolve()
    # A shortcut can start in another folder. Relative folders, such as the spool folder, are next
    # to collector.ini.
    os.chdir(config.parent)
    setup_logging(config.parent)
    if args.uninstall:
        raise SystemExit(uninstall())
    if args.install:
        raise SystemExit(install(config))
    if args.setup:
        # Only the window. A running collector starts again by itself after "Guardar".
        raise SystemExit(0 if setup_window(config) else 1)
    # The Windows program shows the setup window when the folders are missing.
    if getattr(sys, "frozen", False) and needs_setup(config) and not setup_window(config):
        raise SystemExit(1)
    settings = load_settings(config)
    if settings is None:
        raise SystemExit(1)
    if args.check:
        request = urllib.request.Request(
            settings.app_url + "/api/collector/ping",
            headers={"Authorization": f"Bearer {settings.key}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            say(str(json.loads(response.read())))
        return
    # The shortcut "Iniciar Paddock" also starts Real Penalty, also when a collector already runs.
    start_real_penalty(settings)
    if not one_instance():
        say("El colector ya está corriendo. Su ícono está al lado del reloj de Windows.")
        return
    log.info("Paddock collector %s", VERSION)
    if os.name == "nt":
        Tray(config).start()
    try:
        run(settings)
    finally:
        STOP.set()  # The icon goes away.
        release_instance()
    if AGAIN.is_set():
        time.sleep(1.5)  # The icon thread removes the old icon.
        start_again()


if __name__ == "__main__":
    main()
