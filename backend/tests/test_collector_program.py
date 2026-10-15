"""The server collector program in collector/. It runs without Django, so these tests use a
small fake app server."""

import hashlib
import importlib.util
import json
import logging
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "paddock_collector", ROOT / "collector" / "paddock_collector.py"
)
pc = importlib.util.module_from_spec(SPEC)
sys.modules["paddock_collector"] = pc  # The dataclasses need the module by name.
SPEC.loader.exec_module(pc)


def stringw(text: str) -> bytes:
    return bytes([len(text)]) + text.encode("utf-32-le")


def string(text: str) -> bytes:
    return bytes([len(text)]) + text.encode("ascii")


def connection(car_id=3, name="Driver 04", guid="76561190000000004"):
    return (
        bytes([pc.NEW_CONNECTION])
        + stringw(name)
        + stringw(guid)
        + bytes([car_id])
        + string("acura")
        + string("skin")
    )


def test_packets_become_events_with_the_driver():
    drivers = {}
    assert pc.parse_packet(connection(), drivers)["kind"] == "connected"
    lap = struct.pack("<BBIB", pc.LAP_COMPLETED, 3, 189296, 0) + bytes([0]) + struct.pack("<f", 1)
    event = pc.parse_packet(lap, drivers)
    assert event == {
        "kind": "lap_completed",
        "data": {
            "car_id": 3,
            "guid": "76561190000000004",
            "name": "Driver 04",
            "car_model": "acura",
            "lap_ms": 189296,
            "cuts": 0,
        },
    }
    crash = struct.pack(
        "<BBBBf3f3f", pc.CLIENT_EVENT, pc.CE_COLLISION_WITH_CAR, 3, 7, 88.0, 1, 2, 3, 0, 0, 0
    )
    event = pc.parse_packet(crash, drivers)
    assert event["kind"] == "collision_car"
    assert event["data"]["guid"] == "76561190000000004"
    assert event["data"]["other"] == {"car_id": 7}
    assert event["data"]["speed_kmh"] == 88.0


def test_listener_accepts_only_this_computer(tmp_path):
    state = pc.State(tmp_path / "state.sqlite3")
    listener = pc.EventListener(settings(tmp_path), state, "run")
    assert listener.handle(connection(), "192.168.1.50") is None
    assert listener.handle(b"\x49", "127.0.0.1") is None  # A short packet is ignored.
    assert listener.handle(connection(), "127.0.0.1")["kind"] == "connected"
    assert len(state.unsent_events(10)) == 1


def age(path: Path, seconds: int) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


def settings(tmp_path, url="http://127.0.0.1:9"):
    results = tmp_path / "results"
    logs = tmp_path / "logs"
    results.mkdir()
    logs.mkdir()
    return pc.Settings(
        app_url=url,
        key="pcc_test",
        results_dir=results,
        penalty_dir=logs,
        spool_dir=tmp_path / "spool",
        since="2000-01-01",
    )


def test_running_log_waits_until_a_newer_log_starts(tmp_path):
    s = settings(tmp_path)
    result = s.results_dir / "2026_10_11_20_7_RACE.json"
    result.write_text("{}")
    first = s.penalty_dir / "race_penalty_1.log"
    first.write_text("a")
    age(result, 60)
    age(first, 60)
    found = {path.name for path, _ in pc.candidates(s, time.time())}
    assert found == {"2026_10_11_20_7_RACE.json"}  # The log still runs.
    second = s.penalty_dir / "race_penalty_2.log"
    second.write_text("b")
    found = {path.name for path, _ in pc.candidates(s, time.time())}
    assert "race_penalty_1.log" in found and "race_penalty_2.log" not in found


class FakeApp(BaseHTTPRequestHandler):
    fail = True
    received: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if FakeApp.fail:
            self.send_response(503)
            self.end_headers()
            return
        FakeApp.received.append((self.path, self.headers["Authorization"], body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "assigned", "new": 1}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_app():
    FakeApp.fail = True
    FakeApp.received = []
    server = HTTPServer(("127.0.0.1", 0), FakeApp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_outage_keeps_the_file_and_retries(tmp_path, fake_app):
    s = settings(tmp_path, fake_app)
    result = s.results_dir / "2026_10_11_20_7_RACE.json"
    result.write_text('{"x": 1}')
    age(result, 60)
    state = pc.State(tmp_path / "spool-state.sqlite3")
    s.spool_dir.mkdir()
    app = pc.App(s)

    assert pc.spool_files(s, state, time.time()) == 1
    assert pc.upload_pending(app, state) is False  # The app is down.
    assert len(state.unsent_files()) == 1

    FakeApp.fail = False
    assert pc.upload_pending(app, state) is True
    assert state.unsent_files() == []
    path, auth, body = FakeApp.received[0]
    assert (path, auth) == ("/api/collector/files", "Bearer pcc_test")
    assert b'name="kind"\r\n\r\nresult' in body and b'{"x": 1}' in body

    # The same file again is not sent again.
    assert pc.spool_files(s, state, time.time()) == 0


def test_events_go_in_batches_once(tmp_path, fake_app):
    FakeApp.fail = False
    s = settings(tmp_path, fake_app)
    state = pc.State(tmp_path / "state.sqlite3")
    for seq in range(3):
        state.add_event("run", seq, {"kind": "lap_completed", "at": "2026-10-11T22:00:00+00:00"})
    assert pc.upload_pending(pc.App(s), state) is True
    path, _, body = FakeApp.received[0]
    sent = json.loads(body)
    assert path == "/api/collector/events"
    assert [e["seq"] for e in sent["events"]] == [0, 1, 2]
    assert state.unsent_events(10) == []


def car_update(car_id, x, z, n):
    return struct.pack("<BB3f3fBHf", pc.CAR_UPDATE, car_id, x, 0, z, 0, 0, 0, 3, 7000, n)


def new_session():
    return (
        bytes([pc.NEW_SESSION, 4, 0, 0, 1])
        + stringw("Server")
        + string("ks_highlands")
        + string("layout_long")
        + string("Race")
        + bytes([3])
        + struct.pack("<HHHBB", 30, 0, 60, 20, 25)
        + string("3_clear")
        + struct.pack("<i", 0)
    )


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append((data, address))


def test_positions_go_in_chunks_of_five_seconds(tmp_path):
    state = pc.State(tmp_path / "state.sqlite3")
    listener = pc.EventListener(settings(tmp_path), state, "run")
    listener.handle(connection(car_id=3), "127.0.0.1", now=1000.0)
    listener.handle(car_update(3, 10.0, 20.0, 0.1), "127.0.0.1", now=1000.0)
    listener.handle(car_update(3, 12.0, 21.0, 0.11), "127.0.0.1", now=1000.2)
    listener.handle(car_update(7, 1.0, 2.0, 0.5), "127.0.0.1", now=1000.2)
    assert len(state.unsent_events(10)) == 1  # Only the connection so far.
    listener.handle(car_update(3, 14.0, 22.0, 0.12), "127.0.0.1", now=1005.1)
    events = [json.loads(body) for _, _, body in state.unsent_events(10)]
    chunk = events[1]
    assert chunk["kind"] == "positions"
    assert chunk["data"]["cars"]["76561190000000004"] == [
        [0, 10.0, 20.0, 0.1],
        [200, 12.0, 21.0, 0.11],
    ]
    assert chunk["data"]["cars"]["car:7"] == [[200, 1.0, 2.0, 0.5]]


def test_position_request_only_when_turned_on(tmp_path):
    state = pc.State(tmp_path / "state.sqlite3")
    off = pc.EventListener(settings(tmp_path), state, "run")
    off.sock = FakeSocket()
    off.handle(new_session(), "127.0.0.1")
    assert off.sock.sent == []

    (tmp_path / "on").mkdir()
    s = settings(tmp_path / "on")
    s.request_positions, s.server_udp_port = True, 11000
    on = pc.EventListener(s, state, "run2")
    on.sock = FakeSocket()
    assert on.handle(new_session(), "127.0.0.1")["kind"] == "session_started"
    assert on.sock.sent == [(struct.pack("<BH", 200, 200), ("127.0.0.1", 11000))]


def test_new_session_carries_the_weather_and_the_temperatures():
    event = pc.parse_packet(new_session(), {})
    assert event["kind"] == "session_started"
    assert (event["data"]["air_temp_c"], event["data"]["road_temp_c"]) == (20, 25)
    assert event["data"]["weather"] == "3_clear"


def test_sun_angle_becomes_the_time_of_day():
    assert pc.time_of_day(0) == "13:00"
    assert pc.time_of_day(-80) == "08:00"
    assert pc.time_of_day(48) == "16:00"


def test_session_start_reads_the_time_and_the_grip_of_the_server(tmp_path):
    cfg = tmp_path / "server_cfg.ini"
    cfg.write_text(
        "[SERVER]\nNAME=x\nSUN_ANGLE=48\n\n[DYNAMIC_TRACK]\nSESSION_START=89\n", encoding="utf-8"
    )
    assert pc.server_conditions(cfg) == {"time_of_day": "16:00", "grip_pct": 89}
    assert pc.server_conditions(tmp_path / "missing.ini") == {}
    assert pc.server_conditions(None) == {}


# "Enviar al servidor": the collector writes the race setup into the Content Manager preset.

PRESET_CFG = """[SERVER]
NAME=EIST Server - Piston Cup
CARS=tatuusfa1
TRACK=csp/3460/../spa
CONFIG_TRACK=
SUN_ANGLE=-16
MAX_CLIENTS=2
TCP_PORT={port}
WELCOME_MESSAGE=cfg/welcome_SERVER_01.txt

[DYNAMIC_TRACK]
SESSION_START=95

[WEATHER_0]
GRAPHICS=sol_33_heavy_drizzle
BASE_TEMPERATURE_AMBIENT=20
BASE_TEMPERATURE_ROAD=0

[__CM_SERVER]
NAME=EIST Server - Piston Cup

[WEATHER_1]
GRAPHICS=sol_06_overcast
BASE_TEMPERATURE_AMBIENT=26
BASE_TEMPERATURE_ROAD=11
"""

PRESET_ENTRIES = """[CAR_0]
DRIVERNAME=
GUID=
MODEL=trr_lmdh_acura_arx-06
SKIN=meyer_shank_93
BALLAST=0
SPECTATOR_MODE=0
RESTRICTOR=0

[CAR_1]
DRIVERNAME=Race Control
GUID=76561190000000099
MODEL=trr_lmdh_acura_arx-06
SKIN=meyer_shank_93
BALLAST=0
SPECTATOR_MODE=1
RESTRICTOR=0
"""

PRESET_CSP = """[CHAT]
MESSAGES_FILTER = '^RP>'

[RAIN_PREVIEW]
REQUIRED = 1
"""

CONTENT = {
    "round": {"id": 9, "number": 3},
    "track": {"key": "ks_highlands", "layout": "layout_long"},
    "entries": [
        {
            "number": 7,
            "name": "Ana",
            "team": "Rojo",
            "guid": "76561190000000001",
            "model": "trr_lmdh_acura_arx-06",
            "ballast_kg": 15,
            "restrictor_pct": 2,
        },
        {
            "number": 8,
            "name": "Juan",
            "team": "",
            "guid": "76561190000000002",
            "model": "trr_lmh_vanwall",
            "ballast_kg": 0,
            "restrictor_pct": 0,
        },
    ],
    "conditions": {
        "sun_angle": 40,
        "air_temp_c": 24,
        "road_offset_c": 7,
        "grip_pct": 89,
        "weather": "sol_05_broken_clouds",
    },
    "script": {"url": "https://paddock.test/api/script/paddock.lua", "race_code": "code-1"},
    "warnings": [],
}


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture
def preset(tmp_path):
    folder = tmp_path / "server" / "presets" / "SERVER_01"
    folder.mkdir(parents=True)
    (folder / "server_cfg.ini").write_bytes(
        PRESET_CFG.format(port=free_port()).replace("\n", "\r\n").encode()
    )
    (folder / "entry_list.ini").write_text(PRESET_ENTRIES, encoding="utf-8")
    (folder / "csp_extra_options.ini").write_text(PRESET_CSP, encoding="utf-8")
    skins = tmp_path / "server" / "content" / "cars" / "trr_lmh_vanwall" / "skins"
    (skins / "b_skin").mkdir(parents=True)
    (skins / "a_skin").mkdir(parents=True)
    return folder


def test_the_setup_goes_into_the_preset_and_keeps_the_rest(preset):
    backup = pc.write_setup(preset, CONTENT)

    assert (backup / "server_cfg.ini").read_bytes().count(b"sol_33_heavy_drizzle") == 1
    cars = pc.car_blocks((preset / "entry_list.ini").read_text(encoding="utf-8"))
    assert [(c["DRIVERNAME"], c["GUID"], c["BALLAST"], c["RESTRICTOR"]) for c in cars[:2]] == [
        ("Ana", "76561190000000001", "15", "2"),
        ("Juan", "76561190000000002", "0", "0"),
    ]
    assert cars[0]["SKIN"] == "meyer_shank_93"  # The skin of the preset for the same car.
    assert cars[1]["SKIN"] == "a_skin"  # The first skin of a new car.
    # 10 open slots with the league cars in turn, then the spectator slot of the preset.
    open_cars = cars[2:12]
    assert all(c["GUID"] == "" and c["DRIVERNAME"] == "" for c in open_cars)
    assert [c["MODEL"] for c in open_cars[:2]] == ["trr_lmdh_acura_arx-06", "trr_lmh_vanwall"]
    assert open_cars[1]["SKIN"] == "b_skin"  # The free skin, not the one Juan uses.
    assert (cars[12]["DRIVERNAME"], cars[12]["SPECTATOR_MODE"]) == ("Race Control", "1")
    assert len(cars) == 13

    raw = (preset / "server_cfg.ini").read_bytes()
    assert b"\r\n" in raw  # The line end of Content Manager stays.
    cfg = raw.decode().replace("\r\n", "\n")
    assert pc.ini_get(cfg, "SERVER", "TRACK") == "csp/3460/../ks_highlands"
    assert pc.ini_get(cfg, "SERVER", "CONFIG_TRACK") == "layout_long"
    assert pc.ini_get(cfg, "SERVER", "CARS") == "trr_lmdh_acura_arx-06;trr_lmh_vanwall"
    assert pc.ini_get(cfg, "SERVER", "MAX_CLIENTS") == "13"
    assert pc.ini_get(cfg, "SERVER", "SUN_ANGLE") == "40"
    assert pc.ini_get(cfg, "DYNAMIC_TRACK", "SESSION_START") == "89"
    assert pc.ini_get(cfg, "WEATHER_0", "GRAPHICS") == "sol_05_broken_clouds"
    assert pc.ini_get(cfg, "WEATHER_0", "BASE_TEMPERATURE_AMBIENT") == "24"
    assert pc.ini_get(cfg, "WEATHER_0", "BASE_TEMPERATURE_ROAD") == "7"
    assert "[WEATHER_1]" not in cfg  # One weather only: the announced one.
    assert pc.ini_get(cfg, "__CM_SERVER", "NAME") == "EIST Server - Piston Cup"
    assert pc.ini_get(cfg, "SERVER", "WELCOME_MESSAGE") == "cfg/welcome_SERVER_01.txt"

    csp = (preset / "csp_extra_options.ini").read_text(encoding="utf-8")
    assert pc.ini_get(csp, "CHAT", "MESSAGES_FILTER") == "'^RP>'"
    assert pc.ini_get(csp, "SCRIPT_1", "SCRIPT") == "'https://paddock.test/api/script/paddock.lua'"
    assert pc.ini_get(csp, "SCRIPT_1", "raceCode") == "'code-1'"

    # A second push changes the same script section.
    pc.write_setup(preset, {**CONTENT, "script": {**CONTENT["script"], "race_code": "code-2"}})
    csp = (preset / "csp_extra_options.ini").read_text(encoding="utf-8")
    assert pc.ini_get(csp, "SCRIPT_1", "raceCode") == "'code-2'"
    assert "[SCRIPT_2]" not in csp


def test_a_setup_without_weather_keeps_the_weathers_of_the_preset(preset):
    content = {**CONTENT, "conditions": {"air_temp_c": 24}}
    pc.write_setup(preset, content)
    cfg = (preset / "server_cfg.ini").read_text(encoding="utf-8")
    assert pc.ini_get(cfg, "WEATHER_1", "GRAPHICS") == "sol_06_overcast"
    assert pc.ini_get(cfg, "WEATHER_1", "BASE_TEMPERATURE_AMBIENT") == "24"
    assert pc.ini_get(cfg, "SERVER", "SUN_ANGLE") == "-16"


def test_a_running_server_blocks_the_write(preset, monkeypatch):
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    assert pc.server_running(preset) is False
    port = int(
        pc.ini_get((preset / "server_cfg.ini").read_text(encoding="utf-8"), "SERVER", "TCP_PORT")
    )
    busy = socket.socket()
    busy.bind(("0.0.0.0", port))
    busy.listen()
    try:
        assert pc.server_running(preset) is True
    finally:
        busy.close()


class FakeCommands:
    def __init__(self, command):
        self.command = command
        self.reports = []

    def get_command(self):
        return self.command

    def report(self, push_id, status, error=""):
        self.reports.append((push_id, status, error))


def test_the_collector_tells_each_step_one_time(preset, tmp_path, monkeypatch):
    app = FakeCommands({"id": 5, "content": CONTENT})
    (tmp_path / "off").mkdir()
    off = settings(tmp_path / "off")
    reported: dict[int, str] = {}
    pc.handle_command(app, off, reported)
    assert app.reports == [(5, "failed", "writing_disabled")]

    (tmp_path / "on").mkdir()
    on = settings(tmp_path / "on")
    on.preset_dir = preset
    on.write_server_config = True
    reported = {}
    app.reports = []
    monkeypatch.setattr(pc, "server_running", lambda folder: True)
    pc.handle_command(app, on, reported)
    pc.handle_command(app, on, reported)
    assert app.reports == [(5, "waiting", "server_running")]  # One time, not each loop.

    monkeypatch.setattr(pc, "server_running", lambda folder: False)
    pc.handle_command(app, on, reported)
    assert app.reports[-1] == (5, "done", "")
    assert "code-1" in (preset / "csp_extra_options.ini").read_text(encoding="utf-8")


def test_a_name_cannot_add_a_line_to_the_server_files(preset):
    """A line break in a name could add a key such as ADMIN_PASSWORD."""
    bad = {**CONTENT["entries"][0], "name": "Ana\r\nADMIN_PASSWORD=x", "team": "R\nojo"}
    pc.write_setup(preset, {**CONTENT, "entries": [bad]})
    text = (preset / "entry_list.ini").read_text(encoding="utf-8")
    assert "\nADMIN_PASSWORD" not in text
    assert pc.car_blocks(text)[0]["DRIVERNAME"] == "Ana  ADMIN_PASSWORD=x"
    script = {"url": "https://x/api/script/paddock.lua'\n[SERVER]", "race_code": "c'ode"}
    csp = pc.csp_options("", script)
    assert "\n[SERVER]" not in csp
    assert pc.ini_get(csp, "SCRIPT_1", "raceCode") == "'code'"


def test_an_unsafe_car_or_track_name_stops_the_write(preset):
    bad = {**CONTENT["entries"][0], "model": "car\nADMIN_PASSWORD=x"}
    with pytest.raises(ValueError):
        pc.write_setup(preset, {**CONTENT, "entries": [bad]})
    with pytest.raises(ValueError):
        pc.write_setup(preset, {**CONTENT, "track": {"key": "../x\n", "layout": ""}})


# Phase 5: the Windows program


def test_newer_version():
    assert pc.newer("1.10.0", "1.9.3")
    assert not pc.newer("1.1.0", "1.1.0")
    assert not pc.newer("1.0.9", "1.1.0")


def test_an_update_replaces_the_program_and_keeps_the_old_one(tmp_path):
    exe = tmp_path / "paddock-collector.exe"
    exe.write_bytes(b"old")
    new = b"new program"
    pc.apply_update(exe, new, hashlib.sha256(new).hexdigest())
    assert exe.read_bytes() == new
    assert (tmp_path / "paddock-collector.old.exe").read_bytes() == b"old"
    pc.remove_old_program(exe)
    assert not (tmp_path / "paddock-collector.old.exe").exists()


def test_an_update_with_a_wrong_sum_keeps_the_program(tmp_path):
    exe = tmp_path / "paddock-collector.exe"
    exe.write_bytes(b"old")
    with pytest.raises(ValueError):
        pc.apply_update(exe, b"changed", "0" * 64)
    assert exe.read_bytes() == b"old"
    assert not (tmp_path / "paddock-collector.new.exe").exists()


class UpdateApp:
    def __init__(self, version):
        self.version = version
        self.downloads = 0

    def get_version(self):
        return {"version": self.version, "sha256": hashlib.sha256(b"v2").hexdigest()}

    def download_program(self):
        self.downloads += 1
        return b"v2"


def test_check_update_only_for_a_newer_program(tmp_path):
    exe = tmp_path / "paddock-collector.exe"
    exe.write_bytes(b"v1")
    assert not pc.check_update(UpdateApp(pc.VERSION), exe)
    assert not pc.check_update(UpdateApp(None), exe)
    assert not pc.check_update(UpdateApp("99.0.0"), None)  # Python runs the script: no update.
    app = UpdateApp("99.0.0")
    assert pc.check_update(app, exe)
    assert (app.downloads, exe.read_bytes()) == (1, b"v2")


def test_the_shortcut_runs_with_the_full_config_path(tmp_path):
    _target, arguments = pc.launch(tmp_path / "collector.ini")
    assert "--config" in arguments
    assert str((tmp_path / "collector.ini").resolve()) in arguments


def test_install_gives_the_paths_to_powershell_in_variables(tmp_path, monkeypatch):
    config = tmp_path / "collector.ini"
    config.write_text(
        (Path(pc.__file__).parent / "collector.example.ini").read_text("utf-8"), "utf-8"
    )
    seen = {}

    def fake_run(command, env, **kwargs):
        seen.update(command=command, env=env)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pc.subprocess, "run", fake_run)
    monkeypatch.setattr(pc, "say", lambda text: None)
    monkeypatch.setattr(pc, "setup_window", lambda path: True)
    assert pc.install(config) == 0
    assert str(config.resolve()) not in " ".join(seen["command"])  # Not in the script.
    assert seen["env"]["PADDOCK_NAME"] == "Iniciar Paddock.lnk"
    assert str(config.resolve()) in seen["env"]["PADDOCK_ARGS"]


def settings_for_life(**values):
    return SimpleNamespace(**{"stop_after_minutes": 15, "log_stable_seconds": 600, **values})


def test_the_collector_stops_after_the_server_stops():
    life = pc.Lifetime(settings_for_life(), now=0)
    assert not life.done(server_up=False, idle=True, now=3600)  # Before the race: it waits.
    assert not life.done(server_up=True, idle=True, now=4000)
    assert not life.done(server_up=False, idle=True, now=4000 + 899)
    assert not life.done(server_up=False, idle=False, now=4000 + 900)  # Files still to send.
    assert life.done(server_up=False, idle=True, now=4000 + 900)


def test_the_stop_waits_for_the_last_real_penalty_log():
    life = pc.Lifetime(settings_for_life(stop_after_minutes=1, log_stable_seconds=600), now=0)
    life.done(server_up=True, idle=True, now=0)
    assert not life.done(server_up=False, idle=True, now=600)
    assert life.done(server_up=False, idle=True, now=900)


def test_a_forgotten_collector_stops_and_zero_never_stops():
    life = pc.Lifetime(settings_for_life(), now=0)
    assert life.done(server_up=False, idle=True, now=pc.NO_SERVER_SECONDS)
    never = pc.Lifetime(settings_for_life(stop_after_minutes=0), now=0)
    assert not never.done(server_up=False, idle=True, now=10**9)


def test_real_penalty_starts_only_when_it_does_not_run(tmp_path, monkeypatch):
    exe = tmp_path / "ac_penalty.exe"
    exe.write_bytes(b"MZ")
    started = []
    monkeypatch.setattr(pc.subprocess, "Popen", lambda args, **kwargs: started.append(args))
    settings = SimpleNamespace(realpenalty_exe=exe)
    monkeypatch.setattr(pc, "process_running", lambda image: True)
    assert not pc.start_real_penalty(settings)
    monkeypatch.setattr(pc, "process_running", lambda image: False)
    assert pc.start_real_penalty(settings)
    assert started == [[str(exe)]]
    assert not pc.start_real_penalty(SimpleNamespace(realpenalty_exe=None))
    assert not pc.start_real_penalty(SimpleNamespace(realpenalty_exe=tmp_path / "none.exe"))


def test_only_one_collector_runs():
    port = 47999
    assert pc.one_instance(port)
    assert not pc.one_instance(port)
    pc.release_instance()
    assert pc.one_instance(port)
    pc.release_instance()


def test_a_broken_config_gives_a_message(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(pc, "say", messages.append)
    config = tmp_path / "collector.ini"
    config.write_text("[app]\nurl = x\nbroken line\n", encoding="utf-8")
    assert pc.load_settings(config) is None
    assert pc.load_settings(tmp_path / "missing.ini") is None
    assert (
        all(m.startswith("collector.ini tiene un error") for m in messages) and len(messages) == 2
    )


# The setup window


def ac_tree(root):
    ac = root / "steamapps" / "common" / "assettocorsa"
    for folder in (
        "server/results",
        "server/realpenalty/logs",
        "server/presets/OLD",
        "server/presets/SERVER_01",
    ):
        (ac / folder).mkdir(parents=True)
    (ac / "server/realpenalty/ac_penalty.exe").write_bytes(b"MZ")
    (ac / "server/presets/OLD/server_cfg.ini").write_text("[SERVER]\n")
    os.utime(ac / "server/presets/OLD/server_cfg.ini", (1, 1))
    (ac / "server/presets/SERVER_01/server_cfg.ini").write_text("[SERVER]\n")
    return ac


def test_the_steam_libraries_come_from_libraryfolders(tmp_path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    library = tmp_path / "Lib"
    vdf = '"libraryfolders"\n{\n "0" { "path" "' + str(steam).replace("\\", "\\\\") + '" }\n'
    vdf += ' "1" { "path" "' + str(library).replace("\\", "\\\\") + '" }\n}\n'
    (steam / "steamapps" / "libraryfolders.vdf").write_text(vdf)
    assert pc.steam_libraries(steam) == [steam, library]
    ac = ac_tree(library)
    assert pc.find_ac(pc.steam_libraries(steam)) == ac


def test_detect_finds_the_folders_and_the_newest_preset(tmp_path):
    ac = ac_tree(tmp_path)
    found = pc.detect(ac)
    assert found["results_dir"] == str(ac / "server" / "results")
    assert found["realpenalty_exe"].endswith("ac_penalty.exe")
    assert found["realpenalty_logs_dir"].endswith("logs")
    assert found["preset_dir"] == str(ac / "server" / "presets" / "SERVER_01")
    assert pc.setup_problems(found) == []
    assert pc.setup_problems({**found, "results_dir": ""}) == [
        "Falta la carpeta de resultados del servidor."
    ]


def test_save_setup_keeps_the_rest_of_the_file(tmp_path):
    ac = ac_tree(tmp_path)
    config = tmp_path / "collector.ini"
    example = (Path(pc.__file__).parent / "collector.example.ini").read_text("utf-8")
    config.write_text(example.replace("key = pcc_CHANGE_ME", "key = pcc_kept"), "utf-8")
    assert pc.needs_setup(config)
    pc.save_setup(config, pc.detect(ac), write_server=True)
    settings = pc.Settings.load(config)
    assert settings.key == "pcc_kept"
    assert settings.results_dir == ac / "server" / "results"
    assert settings.realpenalty_exe == ac / "server" / "realpenalty" / "ac_penalty.exe"
    assert settings.preset_dir == ac / "server" / "presets" / "SERVER_01"
    assert settings.server_cfg == settings.preset_dir / "server_cfg.ini"
    assert settings.write_server_config is True
    assert not pc.needs_setup(config)


def test_install_stops_when_the_setup_is_cancelled(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(pc, "setup_window", lambda path: False)
    monkeypatch.setattr(pc, "say", messages.append)
    assert pc.install(tmp_path / "collector.ini") == 1
    assert "instalar.bat" in messages[0]


def test_example_paths_take_the_found_paths(tmp_path):
    ac = ac_tree(tmp_path)
    found = pc.detect(ac)
    kept = str(tmp_path)  # A saved path that exists.
    missing = str(tmp_path / "no-such-folder" / "results")  # The example path of collector.ini.
    current = {"results_dir": missing, "realpenalty_exe": "", "preset_dir": kept}
    values = pc.initial_values(current, found)
    assert values["results_dir"] == found["results_dir"]
    assert values["realpenalty_exe"] == found["realpenalty_exe"]
    assert values["preset_dir"] == kept


def test_a_preset_with_csp_options_comes_first(tmp_path):
    ac = ac_tree(tmp_path)
    (ac / "server/presets/OLD/csp_extra_options.ini").write_text("[EXTRA_RULES]")
    assert pc.presets(ac)[0].name == "OLD"


def test_tasklist_runs_with_no_window(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(stdout="acServer.exe  12 Console", returncode=0)

    monkeypatch.setattr(pc.subprocess, "run", fake_run)
    assert pc.process_running("acServer.exe")
    assert seen["creationflags"] == pc.NO_WINDOW


def test_the_preset_list_shows_the_content_manager_name(tmp_path):
    folder = tmp_path / "server" / "presets"
    for name, title in (
        ("SERVER_01", "EIST x:aJnn5d"),
        ("Rain", "EIST x:pNoWAm"),
        ("S3", "Gooners"),
    ):
        (folder / name).mkdir(parents=True)
        (folder / name / "server_cfg.ini").write_text(
            "[SERVER]" + chr(10) + f"NAME={title}" + chr(10)
        )
    (folder / "S4").mkdir()
    (folder / "S4" / "server_cfg.ini").write_text("[SERVER]" + chr(10))
    labels = pc.preset_labels(pc.presets(tmp_path))
    assert set(labels) == {"EIST (SERVER_01)", "EIST (Rain)", "Gooners", "S4"}
    assert pc.preset_label(folder / "S3") == "Gooners"
    assert pc.preset_name(folder / "SERVER_01") == "EIST"


def test_a_push_to_another_preset_writes_it_and_keeps_it(tmp_path, monkeypatch):
    ac = ac_tree(tmp_path)
    folder = ac / "server" / "presets"
    config = tmp_path / "collector.ini"
    example = (Path(pc.__file__).parent / "collector.example.ini").read_text("utf-8")
    config.write_text(example, "utf-8")
    pc.save_setup(config, pc.detect(ac), write_server=True)
    settings = pc.Settings.load(config)
    assert settings.preset_dir == folder / "SERVER_01"
    assert {p["folder"] for p in pc.preset_list(settings)} == {"SERVER_01", "OLD"}
    assert pc.chosen_preset(settings.preset_dir, "OLD") == folder / "OLD"
    assert pc.chosen_preset(settings.preset_dir, "..") is None
    assert pc.chosen_preset(settings.preset_dir, "NOPE") is None

    written = []
    monkeypatch.setattr(pc, "server_running", lambda preset: False)
    monkeypatch.setattr(
        pc, "write_setup", lambda preset, content, open_slots: written.append(preset) or preset
    )
    app = SimpleNamespace(
        get_command=lambda: {"id": 9, "content": {"round": {"number": 1}, "preset": "OLD"}},
        report=lambda push_id, status, error="": reports.append((push_id, status, error)),
    )
    reports = []
    pc.handle_command(app, settings, {})
    assert written == [folder / "OLD"]
    assert reports == [(9, "done", "")]
    assert settings.preset_dir == folder / "OLD"
    assert settings.server_cfg == folder / "OLD" / "server_cfg.ini"
    assert pc.Settings.load(config).preset_dir == folder / "OLD"  # Saved for the next start.

    bad = SimpleNamespace(
        get_command=lambda: {"id": 10, "content": {"round": {"number": 1}, "preset": "../x"}},
        report=lambda push_id, status, error="": reports.append((push_id, status, error)),
    )
    pc.handle_command(bad, settings, {})
    assert reports[-1] == (10, "failed", "unknown_preset")


# The tray icon


def test_the_tray_menu_items(tmp_path):
    config = tmp_path / "collector.ini"
    pc.STOP.clear()
    pc.AGAIN.clear()
    opened = []
    pc.tray_action(pc.MENU_LOG, config, open_file=opened.append)
    assert opened == [str(tmp_path / "collector.log")]
    assert not pc.STOP.is_set()

    pc.tray_action(pc.MENU_SETUP, config, run_setup=lambda: SimpleNamespace(returncode=1))
    assert not pc.STOP.is_set()  # Cancelled: the collector goes on.
    pc.tray_action(pc.MENU_SETUP, config, run_setup=lambda: SimpleNamespace(returncode=0))
    assert pc.STOP.is_set() and pc.AGAIN.is_set()  # Saved: it starts again.

    pc.STOP.clear()
    pc.AGAIN.clear()
    pc.tray_action(pc.MENU_EXIT, config)
    assert pc.STOP.is_set() and not pc.AGAIN.is_set()
    pc.STOP.clear()


def test_the_own_command_runs_the_script_with_python():
    command = pc.own_command("--setup")
    assert command[0] == sys.executable
    assert command[1].endswith("paddock_collector.py")
    assert command[-1] == "--setup"


def test_a_real_penalty_log_waits_for_a_newer_log_of_its_own_series(tmp_path):
    s = settings(tmp_path)
    logs = tmp_path / "logs"
    now = time.time()
    old_output = logs / "output_20261014_204527.log"
    practice_1 = logs / "practice_penalty_20261014_204737.log"
    practice_2 = logs / "practice_penalty_20261014_204841.log"
    for path in (old_output, practice_1, practice_2):
        path.write_text("x")
        os.utime(path, (now, now))  # All are still written.
    names = {path.name for path, _kind in pc.candidates(s, now)}
    # Only the first practice log is finished: a newer practice log exists. The output log is
    # older than both practice logs, but its series has no newer log.
    assert names == {practice_1.name}
    assert pc.log_series(practice_2.name) == "practice_penalty"
    assert pc.log_series("output_20261014_204527.log") == "output"


# Phase 6: the status for the health page


def test_the_status_has_the_queue_and_the_last_error(tmp_path):
    s = settings(tmp_path)
    state = pc.State(tmp_path / "state.sqlite3")
    copy = tmp_path / "copy.json"
    copy.write_text("{}")
    state.add_file("a" * 64, "2026_10_14_21_0_RACE.json", "result", copy)
    handler = pc.LastError()
    record = logging.LogRecord("x", logging.WARNING, "", 0, "Upload failed: HTTP 502", None, None)
    handler.emit(record)
    pc.LAST_ERROR.text, pc.LAST_ERROR.at = handler.text, handler.at
    body = pc.status_body(s, state)
    assert body["queued_files"] == 1
    assert body["last_error"] == "Upload failed: HTTP 502"
    assert body["last_error_at"]
    assert "presets" not in body  # No preset folder in this setup.
    pc.LAST_ERROR.text, pc.LAST_ERROR.at = "", None
