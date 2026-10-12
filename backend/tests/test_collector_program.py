"""The server collector program in collector/. It runs without Django, so these tests use a
small fake app server."""

import importlib.util
import json
import os
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

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
    listener = pc.EventListener(0, state, "run")
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
