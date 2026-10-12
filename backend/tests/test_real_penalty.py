"""The Real Penalty parser against the real, sanitized logs in samples/."""

from pathlib import Path

import pytest

from apps.imports.real_penalty import PenaltyLogError, parse, plan_penalties

LOGS = Path(__file__).resolve().parents[2] / "samples" / "2026-10-11-ks-highlands" / "realpenalty"


def load(name):
    return parse((LOGS / name).read_text(encoding="utf-8"))


def test_all_race_logs_are_race_starts():
    logs = [load(p.name) for p in sorted(LOGS.glob("race_penalty_*.log"))]
    assert len(logs) == 21
    assert {log.session_type for log in logs} == {"race"}
    assert logs[0].track == "ks_highlands / layout_long"
    assert logs[0].minutes == 30
    assert all(log.seconds < 240 for log in logs[:-1])  # 20 starts stopped in less than 4 minutes.
    assert logs[-1].seconds > 30 * 60


def test_final_race_has_a_served_stop_and_go():
    plan = plan_penalties(load("race_penalty_20261011_192731.log"))
    assert [(p.name, p.penalty) for p in plan.served] == [("Driver 03", "Stop & go 5 seconds")]
    assert plan.time == []
    assert plan.dsq == []


def test_abandoned_start_has_time_penalties_at_the_end():
    plan = plan_penalties(load("race_penalty_20261011_190616.log"))
    assert len(plan.time) == 5
    assert {p.seconds for p in plan.time} == {20}
    assert {p.cause for p in plan.not_served} == {"jump"}


def test_qualifying_log_has_an_invalid_lap():
    log = load("qualify_penalty_20261011_183944.log")
    assert log.session_type == "qualifying"
    assert [(lap.name, lap.lap_time_ms) for lap in log.invalid_laps] == [("Driver 05", 336531)]
    assert log.cuts["76561190000000005"] == 2


def test_text_that_is_not_a_log_is_refused():
    with pytest.raises(PenaltyLogError):
        parse("hello")
