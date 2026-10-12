"""The driver collector program in collector/. The tests feed samples without AC."""

import ctypes
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "driver_collector", ROOT / "collector" / "driver_collector.py"
)
dc = importlib.util.module_from_spec(SPEC)
sys.modules["driver_collector"] = dc  # The dataclasses need the module by name.
SPEC.loader.exec_module(dc)


def sample(laps, lap_ms, live=True, last=0):
    return dc.Sample(
        live=live,
        session=2,
        completed_laps=laps,
        lap_ms=lap_ms,
        last_lap_ms=last,
        pos=lap_ms / 1000,
        speed_kmh=200.0,
        gas=1.0,
        brake=0.0,
        steer=0.01,
        gear=5,
        rpm=8000,
        track="ks_highlands",
        car="acura",
    )


def test_shared_memory_layout_matches_ac():
    # The offsets of the AC SDK: the lap counter after three ints and four 15-character texts.
    assert dc.Graphics.completed_laps.offset == 3 * 4 + 4 * 15 * 2
    assert dc.Graphics.normalized_car_position.offset == 248
    assert dc.Physics.speed_kmh.offset == 28
    assert dc.Static.track.offset == 15 * 2 * 2 + 8 + 33 * 2


def test_recorder_gives_a_lap_when_the_counter_goes_up():
    recorder = dc.Recorder(hz=20)
    assert recorder.feed(sample(0, 0, live=False)) is None
    assert recorder.status == "waiting"
    for ms in (100, 200, 300):
        assert recorder.feed(sample(0, ms)) is None
    assert recorder.status == "recording"
    lap = recorder.feed(sample(1, 50, last=189296))
    assert lap["lap_number"] == 1
    assert lap["lap_time_ms"] == 189296
    assert lap["session_type"] == "race"
    assert lap["channels"]["t_ms"] == [100, 200, 300]
    assert set(lap["channels"]) == {
        "t_ms",
        "pos",
        "speed_kmh",
        "gas",
        "brake",
        "steer",
        "gear",
        "rpm",
    }
    # The new lap starts with the sample that ended the old one.
    assert recorder.channels["t_ms"] == [50]


def test_session_change_gives_no_fake_lap():
    recorder = dc.Recorder(hz=20)
    recorder.feed(sample(5, 100))
    recorder.feed(sample(5, 200))
    assert recorder.feed(sample(0, 10)) is None  # A new session starts the counter again.


def test_spool_files_appear_whole(tmp_path):
    spool = dc.Spool(tmp_path)
    path = spool.add({"lap_number": 2, "channels": {}})
    assert path.suffix == ".json"
    assert json.loads(path.read_text())["lap_number"] == 2
    assert not list(tmp_path.glob("*.tmp"))
    spool.done(path)
    assert spool.waiting() == []


def test_wide_text_reads_until_the_end_mark():
    value = (ctypes.c_uint16 * 33)(*[ord(c) for c in "ks_highlands"])
    assert dc.text(value) == "ks_highlands"
