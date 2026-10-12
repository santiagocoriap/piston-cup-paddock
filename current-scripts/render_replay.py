#!/usr/bin/env python3
"""Render a scrubbable HTML replay from a live_logger.py telemetry capture.

Projects recorded world positions onto the track's own minimap image using
AC's own coordinate transform (content/tracks/<track>/<config>/data/map.ini:
X_OFFSET, Z_OFFSET, SCALE_FACTOR -- the same formula AC's own minimap uses),
and animates one colored dot per driver along a time scrubber.

Only works for sessions captured by live_logger.py -- there is no telemetry
to replay for races that ran before that logger was wired in. A few extra
features opportunistically enrich the replay when matching files happen to
exist for the same session, found by timestamp proximity (there's no shared
session ID across any of these on-disk formats):
  - Per-lap sector splits: AC's own server/results/<...>.json ("Laps"/
    "Sectors") -- the UDP telemetry alone has no sector-crossing events.
  - Pit lane in/out timestamps: the RealPenalty plugin's
    server/realpenalty/logs/<type>_penalty_*.log ("Pit lane entered"/"Pit
    stop"/"Pit lane left") -- stock AC's UDP protocol has no pit flag at all.
  - Crashes: live_logger.py's own *_crashes.csv if the capture is new enough
    to have one (ACSP_CLIENT_EVENT), else a best-effort fallback that matches
    the results JSON's untimed "Events" list to the closest recorded position
    per driver.
There is no real yellow-flag/safety-car state available anywhere -- AC's
dynamic flag rules are client-side only and never cross the UDP plugin
protocol, so that's not attempted here.

Usage:
    python render_replay.py [session_name] [--telemetry-dir telemetry] [--out OUT.html]

If no session_name is given, the most recently modified *_positions.csv in
the telemetry directory is used.
"""
import argparse
import base64
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from generate_report import (
    DRIVER_PALETTE, driver_code, esc, fmt_ms,
    build_tables, compute_sector_bests, find_penalty_log,
    _PENALTY_LOG_TS_RE, _PIT_ENTER_RE, _PIT_STOP_RE, _PIT_LEFT_RE,
)


def _json_default(o):
    """pandas/numpy scalars (e.g. numpy.int64 from a DataFrame column) leak
    through generate_report.py's sector/lap-best helpers -- unwrap them."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def parse_map_ini(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    values = {}
    for m in re.finditer(r"^([A-Z_]+)\s*=\s*([-\d.]+)", text, re.MULTILINE):
        values[m.group(1)] = float(m.group(2))
    return values


def find_map_assets(ac_root: Path, track: str, config: str):
    base = ac_root / "content" / "tracks" / track
    candidates = [base / config, base] if config else [base]
    for c in candidates:
        map_png = c / "map.png"
        map_ini = c / "data" / "map.ini"
        if map_png.exists() and map_ini.exists():
            return map_png, map_ini
    return None, None


def session_start_datetime(session_name):
    """live_logger.py always prefixes session_name with its own
    time.strftime('%Y%m%d_%H%M%S') capture, regardless of what's in the
    track/session name after it."""
    return datetime.strptime(session_name[:15], "%Y%m%d_%H%M%S")


def load_session(telemetry_dir: Path, session_name: str):
    meta = json.loads((telemetry_dir / f"{session_name}_meta.json").read_text(encoding="utf-8"))
    positions = []
    with open(telemetry_dir / f"{session_name}_positions.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            positions.append({
                "t": int(row["t_ms"]), "car_id": int(row["car_id"]),
                "x": float(row["x"]), "z": float(row["z"]),
                "n": float(row["norm_pos"]) if row.get("norm_pos") not in (None, "") else None,
            })
    laps = []
    lap_path = telemetry_dir / f"{session_name}_laps.csv"
    if lap_path.exists():
        with open(lap_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                laps.append({"t": int(row["t_ms"]), "car_id": int(row["car_id"]),
                              "lap_time_ms": int(row["lap_time_ms"]),
                              "cuts": int(row.get("cuts") or 0)})

    # None (not []) means "no crash file at all" -- an old capture predating
    # the _crashes.csv format -- as opposed to a genuine zero-crash race.
    crashes = None
    crash_path = telemetry_dir / f"{session_name}_crashes.csv"
    if crash_path.exists():
        crashes = []
        with open(crash_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                crashes.append({
                    "t": int(row["t_ms"]), "car_id": int(row["car_id"]), "kind": row["kind"],
                    "other_car_id": int(row["other_car_id"]) if row.get("other_car_id") else None,
                    "speed": float(row["impact_speed"]), "x": float(row["x"]), "z": float(row["z"]),
                })
    return meta, positions, laps, crashes


def find_results_json(server_dir: Path, session_start: datetime, max_t_ms: int):
    """Match purely by mtime proximity to the session's estimated end time --
    there's no session ID shared between live_logger.py's telemetry and AC's
    own results JSON. Session names/types are server-admin-chosen free text,
    so they aren't a reliable join key either."""
    results_dir = server_dir / "results"
    if not results_dir.exists():
        return None
    target = session_start.timestamp() + max_t_ms / 1000
    best, best_diff = None, None
    for p in results_dir.glob("*.json"):
        try:
            diff = abs(p.stat().st_mtime - target)
        except OSError:
            continue
        if best_diff is None or diff < best_diff:
            best, best_diff = p, diff
    return best if best is not None and best_diff <= 180 else None


def parse_pit_events(path: Path, session_start: datetime):
    """Real pit lane in/out timestamps from the RealPenalty plugin's log --
    stock AC's UDP protocol has no pit flag at all. Returns
    {guid: [{"in_t": ms, "out_t": ms|None, "serviced": bool}]} with times
    converted to session-elapsed ms to line up with the telemetry's own
    clock."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    pending, events = {}, {}
    for line in text.splitlines():
        ts_m = _PENALTY_LOG_TS_RE.match(line)
        if not ts_m:
            continue
        try:
            t_ms = int((datetime.fromisoformat(ts_m.group(1)) - session_start).total_seconds() * 1000)
        except ValueError:
            continue
        m = _PIT_ENTER_RE.search(line)
        if m:
            pending[m.group(1)] = {"in_t": t_ms, "serviced": False}
            continue
        m = _PIT_STOP_RE.search(line)
        if m:
            p = pending.get(m.group(1))
            if p:
                p["serviced"] = True
            continue
        m = _PIT_LEFT_RE.search(line)
        if m:
            guid = m.group(1)
            p = pending.pop(guid, None)
            if p:
                events.setdefault(guid, []).append(
                    {"in_t": p["in_t"], "out_t": t_ms, "serviced": p["serviced"]})
            continue
    for guid, p in pending.items():
        events.setdefault(guid, []).append({"in_t": p["in_t"], "out_t": None, "serviced": p["serviced"]})
    for v in events.values():
        v.sort(key=lambda e: e["in_t"])
    return events


def crashes_from_events(data, car_by_guid, raw_tracks):
    """Best-effort fallback for sessions captured before live_logger.py
    recorded ACSP_CLIENT_EVENT directly: AC's results JSON logs every
    collision under "Events" but with no timestamp or lap number at all, so
    the closest recorded position for that driver is used as a stand-in.
    Marked approx=True since this can occasionally pick the wrong lap if a
    driver crashed in the exact same spot more than once."""
    out = []
    used = {}
    for e in data.get("Events", []):
        guid = (e.get("Driver") or {}).get("Guid")
        etype = e.get("Type")
        car_id = car_by_guid.get(guid)
        if car_id is None or etype not in ("COLLISION_WITH_CAR", "COLLISION_WITH_ENV"):
            continue
        pts = raw_tracks.get(car_id)
        if not pts:
            continue
        wp = e.get("WorldPosition") or {}
        ex, ez = wp.get("X", 0), wp.get("Z", 0)
        consumed = used.setdefault(car_id, set())
        best_idx, best_d = None, None
        for i, p in enumerate(pts):
            if i in consumed:
                continue
            d = (p["x"] - ex) ** 2 + (p["z"] - ez) ** 2
            if best_d is None or d < best_d:
                best_d, best_idx = d, i
        if best_idx is None or best_d > 400:  # > 20m off -- not a confident match
            continue
        consumed.add(best_idx)
        other_guid = (e.get("OtherDriver") or {}).get("Guid")
        out.append({
            "t": pts[best_idx]["t"], "car_id": car_id,
            "kind": "car" if etype == "COLLISION_WITH_CAR" else "env",
            "other_car_id": car_by_guid.get(other_guid), "speed": e.get("ImpactSpeed") or 0,
            "x": ex, "z": ez, "approx": True,
        })
    out.sort(key=lambda c: c["t"])
    return out


def build_driver_styles(meta):
    used_codes = set()
    styles = {}
    for i, (cid, d) in enumerate(sorted(meta["drivers"].items(), key=lambda kv: int(kv[0]))):
        styles[int(cid)] = {
            "color": DRIVER_PALETTE[i % len(DRIVER_PALETTE)],
            "code": driver_code(d["name"], used_codes),
            "name": d["name"],
            "guid": d["guid"],
        }
    return styles


def build_best_laps(laps, tracks, min_points=5):
    """Each driver's fastest lap (clean laps preferred), as a trace sorted by
    norm_pos (not time) so the compare view can line two drivers up by track
    position rather than by wall-clock time."""
    by_car = {}
    for l in laps:
        by_car.setdefault(l["car_id"], []).append(l)
    best = {}
    for car_id, car_laps in by_car.items():
        pool = [l for l in car_laps if l["cuts"] == 0] or car_laps
        lap = min(pool, key=lambda l: l["lap_time_ms"])
        start_t, end_t = lap["t"] - lap["lap_time_ms"], lap["t"]
        pts = [p for p in tracks.get(car_id, []) if start_t <= p["t"] <= end_t and p["n"] is not None]
        if len(pts) < min_points:
            continue
        trace = sorted(
            ({"n": p["n"], "px": p["px"], "py": p["py"], "tRel": p["t"] - start_t} for p in pts),
            key=lambda r: r["n"])
        best[car_id] = {"lapTimeMs": lap["lap_time_ms"], "trace": trace}
    return best


def build_lap_timeline(laps, laps_df):
    """Our own lap-completion markers (always available), enriched with AC's
    real per-lap Sectors from the matched results JSON when there is one --
    zipped in completion order per car since there's no shared lap ID, so a
    reconnect/car-swap mid-session could misalign sectors by a lap or two."""
    by_car = {}
    for l in laps:
        by_car.setdefault(l["car_id"], []).append(l)
    for v in by_car.values():
        v.sort(key=lambda l: l["t"])

    sectors_by_car = {}
    if laps_df is not None and not laps_df.empty and "Sectors" in laps_df.columns:
        for _, row in laps_df.sort_values(["CarId", "lap_number"]).iterrows():
            sectors_by_car.setdefault(int(row["CarId"]), []).append(row.get("Sectors") or None)

    timeline = {}
    for car_id, car_laps in by_car.items():
        secs = sectors_by_car.get(car_id, [])
        rows = [{
            "t": l["t"], "lapNumber": i + 1, "lapTimeMs": l["lap_time_ms"], "cuts": l["cuts"],
            "sectors": secs[i] if i < len(secs) else None,
        } for i, l in enumerate(car_laps)]
        timeline[car_id] = rows
    return timeline


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title} — Replay</title>
<style>
  :root {{ --surface-1:#1a1a19; --surface-2:#232320; --page:#0d0d0d; --text-primary:#fff; --text-secondary:#c3c2b7;
           --baseline:#454542; --border:rgba(255,255,255,0.1); --purple:#9085e9; --green:#4caf4c; --red:#e66767; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:28px 16px 48px; background:var(--page); color:var(--text-primary);
          font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 0 0 10px; }}
  .subtitle {{ color: var(--text-secondary); font-size: 13px; margin: 0 0 18px; }}
  .hint {{ color: var(--text-secondary); font-size: 12px; margin: 0 0 10px; }}
  .card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 18px; margin-bottom: 16px; }}
  .race-clock {{ font-size: 13px; font-weight: 700; color: var(--text-secondary); text-align: center; margin-bottom: 10px; }}
  .map-box {{ position: relative; width: 100%; max-width: 760px; margin: 0 auto; overflow: hidden; border-radius: 6px; }}
  .zoom-inner {{ position: relative; width: 100%; transform-origin: 0 0; }}
  .map-box img {{ width: 100%; display: block; }}
  .dot {{ position: absolute; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%;
          border: 2px solid var(--page); transition: none; }}
  .dot-label {{ position: absolute; font-size: 10px; font-weight: 700; margin-top: -22px; margin-left: -8px;
                white-space: nowrap; text-shadow: 0 0 3px #000, 0 0 3px #000; }}
  .crash-marker {{ position: absolute; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
                    border: 2px solid var(--red); display: none; pointer-events: none;
                    box-shadow: 0 0 10px var(--red); }}
  .controls {{ display: flex; align-items: center; gap: 12px; margin-top: 16px; }}
  .controls button {{ background: var(--baseline); border: none; color: white; border-radius: 6px;
                        padding: 8px 14px; cursor: pointer; font-weight: 700; }}
  .controls button.toggle-btn {{ background: var(--surface-2); }}
  .controls input[type=range] {{ flex: 1; }}
  .controls select {{ background: var(--surface-1); color: white; border: 1px solid var(--baseline); border-radius: 6px; padding: 6px; }}
  .time {{ font-variant-numeric: tabular-nums; font-size: 13px; color: var(--text-secondary); min-width: 110px; text-align: right; }}
  .legend {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
  .legend .key {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary);
                  background: var(--surface-2); border: 1px solid var(--border); border-radius: 20px;
                  padding: 5px 10px 5px 6px; cursor: pointer; user-select: none; }}
  .legend .key.off {{ opacity: 0.35; }}
  .legend .dot-sw {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }}
  .legend-actions {{ margin-top: 8px; display: flex; gap: 8px; }}
  .legend-actions button {{ background: none; border: none; color: var(--text-secondary); font-size: 12px;
                             text-decoration: underline; cursor: pointer; padding: 0; }}
  table.detail {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  table.detail th, table.detail td {{ padding: 6px 8px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  table.detail th:first-child, table.detail td:first-child {{ text-align: left; }}
  table.detail th {{ color: var(--text-secondary); font-weight: 600; }}
  .sector-best {{ color: var(--purple); font-weight: 700; }}
  .sector-pb {{ color: var(--green); font-weight: 700; }}
  .pit-live {{ color: var(--red); font-weight: 700; }}
  .crash-log {{ list-style: none; margin: 0; padding: 0; font-size: 12px; max-height: 180px; overflow-y: auto; }}
  .crash-log li {{ display: flex; gap: 8px; padding: 6px 4px; border-bottom: 1px solid var(--border); cursor: pointer; }}
  .crash-log li:hover {{ background: var(--surface-2); }}
  .crash-log .ct {{ color: var(--text-secondary); min-width: 50px; }}
  .compare-card {{ display: none; }}
  .compare-grid {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .compare-col {{ flex: 1; min-width: 280px; }}
  .compare-col select {{ width: 100%; margin-bottom: 8px; background: var(--surface-1); color: white;
                          border: 1px solid var(--baseline); border-radius: 6px; padding: 6px; }}
  .delta-readout {{ text-align: center; font-size: 18px; font-weight: 800; margin: 12px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <p class="subtitle">Replay reconstructed from live telemetry — {n_drivers} drivers, {duration_s:.0f}s captured</p>

  <div class="card">
    <div class="race-clock" id="raceClock"></div>
    <div class="map-box">
      <div class="zoom-inner">
        <img src="data:image/png;base64,{map_b64}" alt="Track map">
        <div id="dots"></div>
        <div id="crashMarkers"></div>
      </div>
    </div>
    <div class="controls">
      <button id="playBtn">Play</button>
      <input type="range" id="scrubber" min="0" max="{max_t}" value="0" step="50">
      <select id="speed">
        <option value="1">1x</option>
        <option value="2">2x</option>
        <option value="4" selected>4x</option>
        <option value="8">8x</option>
      </select>
      <span class="time" id="timeLabel">0:00</span>
    </div>
    <div class="legend" id="legend"></div>
    <div class="legend-actions">
      <button id="showAll">Show all</button>
      <button id="showNone">Hide all</button>
    </div>
  </div>

  <div class="card">
    <h2>Driver timing</h2>
    <p class="hint" id="sectorHint">{sector_hint}</p>
    <div style="overflow-x:auto">
      <table class="detail">
        <thead><tr><th>Driver</th><th>Current lap</th><th>Total</th><th>S1</th><th>S2</th><th>S3</th><th>Last lap</th><th>Pit</th></tr></thead>
        <tbody id="detailBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card" id="crashCard" style="display:{crash_card_display}">
    <h2>Crashes</h2>
    <p class="hint">{crash_hint}</p>
    <ul class="crash-log" id="crashLog"></ul>
  </div>

  <div class="card">
    <button class="toggle-btn" id="compareToggle" {compare_disabled}>Compare best laps</button>
  </div>

  <div class="card compare-card" id="compareCard">
    <h2>Best lap comparison</h2>
    <p class="hint">Synced by track position (not time) so the gap at any point shows where time was really gained or lost.</p>
    <div class="compare-grid">
      <div class="compare-col">
        <select id="cmpA"></select>
        <div class="map-box"><div class="zoom-inner" id="cmpZoomA">
          <img src="data:image/png;base64,{map_b64}" alt="Track map">
          <div class="dot" id="cmpDotA"></div>
        </div></div>
      </div>
      <div class="compare-col">
        <select id="cmpB"></select>
        <div class="map-box"><div class="zoom-inner" id="cmpZoomB">
          <img src="data:image/png;base64,{map_b64}" alt="Track map">
          <div class="dot" id="cmpDotB"></div>
        </div></div>
      </div>
    </div>
    <div class="delta-readout" id="deltaReadout"></div>
    <div class="controls">
      <button id="cmpPlayBtn">Play</button>
      <input type="range" id="cmpScrubber" min="0" max="1000" value="0" step="1">
      <select id="cmpSpeed">
        <option value="0.25">0.25x</option>
        <option value="0.5" selected>0.5x</option>
        <option value="1">1x</option>
      </select>
      <span class="time" id="cmpTimeLabel">0:00.000</span>
    </div>
  </div>
</div>
<script>
const DATA = {data_json};

function fmtClock(ms) {{
  if (ms == null) return "—";
  const neg = ms < 0; ms = Math.abs(ms);
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  return (neg ? "-" : "") + m + ":" + (s - m * 60).toFixed(3).padStart(6, "0");
}}
function fmtShort(ms) {{
  const s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}}

function interpBy(points, key, v) {{
  if (!points || !points.length) return null;
  if (v <= points[0][key]) return points[0];
  if (v >= points[points.length - 1][key]) return points[points.length - 1];
  let lo = 0, hi = points.length - 1;
  while (hi - lo > 1) {{
    const mid = (lo + hi) >> 1;
    if (points[mid][key] <= v) lo = mid; else hi = mid;
  }}
  const a = points[lo], b = points[hi];
  const f = (v - a[key]) / Math.max(b[key] - a[key], 1e-6);
  const out = {{}};
  for (const k in a) out[k] = a[k] + (b[k] - a[k]) * f;
  return out;
}}

// --- Main replay -----------------------------------------------------------
const dotsEl = document.getElementById("dots");
const crashMarkersEl = document.getElementById("crashMarkers");
const scrubber = document.getElementById("scrubber");
const playBtn = document.getElementById("playBtn");
const speedSel = document.getElementById("speed");
const timeLabel = document.getElementById("timeLabel");
const raceClock = document.getElementById("raceClock");
const legendEl = document.getElementById("legend");
const detailBody = document.getElementById("detailBody");
const crashLogEl = document.getElementById("crashLog");

const hidden = new Set();
const dotEls = {{}};
const lastPointT = {{}};
DATA.drivers.forEach(d => {{
  const dot = document.createElement("div");
  dot.className = "dot";
  dot.style.background = d.color;
  dotsEl.appendChild(dot);
  const label = document.createElement("div");
  label.className = "dot-label";
  label.style.color = d.color;
  label.textContent = d.code;
  dotsEl.appendChild(label);
  dotEls[d.carId] = {{ dot, label }};
  const pts = DATA.tracks[d.carId] || [];
  lastPointT[d.carId] = pts.length ? pts[pts.length - 1].t : 0;

  const key = document.createElement("span");
  key.className = "key";
  key.innerHTML = '<span class="dot-sw" style="background:' + d.color + '"></span>' + d.code + " — " + d.name;
  key.addEventListener("click", () => {{
    if (hidden.has(d.carId)) hidden.delete(d.carId); else hidden.add(d.carId);
    key.classList.toggle("off", hidden.has(d.carId));
    render(parseFloat(scrubber.value));
  }});
  legendEl.appendChild(key);
}});
document.getElementById("showAll").addEventListener("click", () => {{
  hidden.clear();
  legendEl.querySelectorAll(".key").forEach(k => k.classList.remove("off"));
  render(parseFloat(scrubber.value));
}});
document.getElementById("showNone").addEventListener("click", () => {{
  DATA.drivers.forEach(d => hidden.add(d.carId));
  legendEl.querySelectorAll(".key").forEach(k => k.classList.add("off"));
  render(parseFloat(scrubber.value));
}});

const crashMarkerEls = (DATA.crashes || []).map(c => {{
  const el = document.createElement("div");
  el.className = "crash-marker";
  el.style.left = (c.px * 100) + "%";
  el.style.top = (c.py * 100) + "%";
  crashMarkersEl.appendChild(el);
  return el;
}});
(DATA.crashes || []).forEach(c => {{
  const d = DATA.driversByCarId[c.carId];
  const other = c.otherCarId != null ? DATA.driversByCarId[c.otherCarId] : null;
  const li = document.createElement("li");
  li.innerHTML = '<span class="ct">' + fmtShort(c.t) + "</span><span>" +
    (d ? d.code : "?") + (c.kind === "car" ? " hit " + (other ? other.code : "another car") : " hit the environment") +
    " at " + c.speed.toFixed(0) + " km/h" + (c.approx ? " (approx. time)" : "") + "</span>";
  li.addEventListener("click", () => {{
    scrubber.value = Math.max(c.t - 2000, 0);
    render(parseFloat(scrubber.value));
  }});
  crashLogEl.appendChild(li);
}});

function sectorCellClass(v, overallBest, personalBest) {{
  if (v == null) return "";
  if (overallBest != null && v === overallBest) return "sector-best";
  if (personalBest != null && v === personalBest) return "sector-pb";
  return "";
}}

function lapsCompletedAt(carId, t) {{
  const rows = DATA.lapTimeline[carId] || [];
  let n = 0;
  for (const r of rows) {{ if (r.t <= t) n++; else break; }}
  return n;
}}

function pitStateAt(carId, t) {{
  for (const p of (DATA.pits[carId] || [])) {{
    if (p.in_t <= t && (p.out_t == null || t <= p.out_t)) return p;
  }}
  return null;
}}

function updateRaceClock(t) {{
  if (DATA.session.timeMin > 0) {{
    const remain = Math.max(DATA.session.timeMin * 60000 - t, 0);
    raceClock.textContent = "Time remaining: " + fmtClock(remain);
  }} else if (DATA.session.laps > 0) {{
    let leaderLaps = 0;
    DATA.drivers.forEach(d => {{ leaderLaps = Math.max(leaderLaps, lapsCompletedAt(d.carId, t)); }});
    const remain = Math.max(DATA.session.laps - leaderLaps, 0);
    raceClock.textContent = remain + (remain === 1 ? " lap remaining" : " laps remaining");
  }} else {{
    raceClock.textContent = "";
  }}
}}

function updateDetail(t) {{
  detailBody.innerHTML = "";
  DATA.drivers.forEach(d => {{
    if (hidden.has(d.carId)) return;
    const rows = DATA.lapTimeline[d.carId] || [];
    let completed = 0;
    while (completed < rows.length && rows[completed].t <= t) completed++;
    const last = completed > 0 ? rows[completed - 1] : null;
    const stillRunning = t <= lastPointT[d.carId] + 2000;
    const lapStartT = last ? last.t : 0;
    const curLap = stillRunning ? fmtClock(t - lapStartT) : "—";
    const total = fmtClock(Math.min(t, lastPointT[d.carId]));
    const sectors = (last && last.sectors) || [null, null, null];
    const pb = DATA.session.personalSectors[d.carId] || [null, null, null];
    const ob = DATA.session.overallSectors || [null, null, null];
    const sectorCells = [0, 1, 2].map(i => {{
      const v = sectors[i];
      const cls = sectorCellClass(v, ob[i], pb[i]);
      return '<td class="' + cls + '">' + (v != null ? fmtClock(v) : "—") + "</td>";
    }}).join("");
    const lastLap = last ? fmtClock(last.lapTimeMs) : "—";
    const pit = pitStateAt(d.carId, t);
    const pitCell = pit ? '<span class="pit-live">IN PITS ' + ((t - pit.in_t) / 1000).toFixed(0) + "s</span>" : "—";
    const tr = document.createElement("tr");
    tr.innerHTML = '<td style="color:' + d.color + '">' + d.code + "</td><td>" + curLap + "</td><td>" + total +
      "</td>" + sectorCells + "<td>" + lastLap + "</td><td>" + pitCell + "</td>";
    detailBody.appendChild(tr);
  }});
}}

function render(t) {{
  DATA.drivers.forEach(d => {{
    const els = dotEls[d.carId];
    if (hidden.has(d.carId)) {{ els.dot.style.display = els.label.style.display = "none"; return; }}
    const p = interpBy(DATA.tracks[d.carId] || [], "t", t);
    if (!p) {{ els.dot.style.display = els.label.style.display = "none"; return; }}
    els.dot.style.display = els.label.style.display = "block";
    els.dot.style.left = els.label.style.left = (p.px * 100) + "%";
    els.dot.style.top = els.label.style.top = (p.py * 100) + "%";
  }});
  (DATA.crashes || []).forEach((c, i) => {{
    crashMarkerEls[i].style.display = (t >= c.t - 300 && t <= c.t + 2500) ? "block" : "none";
  }});
  timeLabel.textContent = fmtShort(t);
  updateRaceClock(t);
  updateDetail(t);
}}

let playing = false, lastFrame = null;
function tick(ts) {{
  if (!playing) return;
  if (lastFrame === null) lastFrame = ts;
  const dt = (ts - lastFrame) * parseFloat(speedSel.value);
  lastFrame = ts;
  let t = parseFloat(scrubber.value) + dt;
  if (t > parseFloat(scrubber.max)) t = 0;
  scrubber.value = t;
  render(t);
  requestAnimationFrame(tick);
}}
playBtn.addEventListener("click", () => {{
  playing = !playing;
  playBtn.textContent = playing ? "Pause" : "Play";
  lastFrame = null;
  if (playing) requestAnimationFrame(tick);
}});
scrubber.addEventListener("input", () => render(parseFloat(scrubber.value)));
render(0);

// --- Best-lap comparison ----------------------------------------------------
const compareToggle = document.getElementById("compareToggle");
const compareCard = document.getElementById("compareCard");
const cmpA = document.getElementById("cmpA");
const cmpB = document.getElementById("cmpB");
const cmpDotA = document.getElementById("cmpDotA");
const cmpDotB = document.getElementById("cmpDotB");
const cmpZoomA = document.getElementById("cmpZoomA");
const cmpZoomB = document.getElementById("cmpZoomB");
const cmpScrubber = document.getElementById("cmpScrubber");
const cmpPlayBtn = document.getElementById("cmpPlayBtn");
const cmpSpeedSel = document.getElementById("cmpSpeed");
const cmpTimeLabel = document.getElementById("cmpTimeLabel");
const deltaReadout = document.getElementById("deltaReadout");

const bestLapCarIds = Object.keys(DATA.bestLaps);
compareToggle.addEventListener("click", () => {{
  const showing = compareCard.style.display === "block";
  compareCard.style.display = showing ? "none" : "block";
  compareToggle.textContent = showing ? "Compare best laps" : "Hide comparison";
}});

if (bestLapCarIds.length >= 2) {{
  const sorted = bestLapCarIds.slice().sort((a, b) => DATA.bestLaps[a].lapTimeMs - DATA.bestLaps[b].lapTimeMs);
  [cmpA, cmpB].forEach((sel, idx) => {{
    bestLapCarIds.forEach(cid => {{
      const opt = document.createElement("option");
      opt.value = cid;
      const d = DATA.driversByCarId[cid];
      opt.textContent = d.code + " — " + d.name + " (" + fmtClock(DATA.bestLaps[cid].lapTimeMs) + ")";
      sel.appendChild(opt);
    }});
    sel.value = sorted[idx];
  }});

  function applyZoom(el, bbox) {{
    const pad = 0.08;
    const w = Math.max(bbox.maxX - bbox.minX, 0.02) * (1 + pad * 2);
    const h = Math.max(bbox.maxY - bbox.minY, 0.02) * (1 + pad * 2);
    const scale = Math.min(1 / w, 1 / h);
    const cx = (bbox.minX + bbox.maxX) / 2, cy = (bbox.minY + bbox.maxY) / 2;
    el.style.transform = "scale(" + scale + ") translate(" + ((0.5 - cx) * 100) + "%, " + ((0.5 - cy) * 100) + "%)";
  }}

  let traceA, traceB, styleA, styleB;
  function refreshCompare() {{
    const carA = cmpA.value, carB = cmpB.value;
    traceA = DATA.bestLaps[carA].trace;
    traceB = DATA.bestLaps[carB].trace;
    styleA = DATA.driversByCarId[carA];
    styleB = DATA.driversByCarId[carB];
    cmpDotA.style.background = styleA.color;
    cmpDotB.style.background = styleB.color;
    const xs = traceA.concat(traceB).map(p => p.px), ys = traceA.concat(traceB).map(p => p.py);
    const bbox = {{ minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }};
    applyZoom(cmpZoomA, bbox);
    applyZoom(cmpZoomB, bbox);
    cmpScrubber.max = traceA[traceA.length - 1].tRel;
    cmpScrubber.value = 0;
    renderCompare(0);
  }}
  cmpA.addEventListener("change", refreshCompare);
  cmpB.addEventListener("change", refreshCompare);

  function renderCompare(relMs) {{
    const pA = interpBy(traceA, "tRel", relMs);
    const n = pA.n;
    const pB = interpBy(traceB, "n", n);
    cmpDotA.style.left = (pA.px * 100) + "%"; cmpDotA.style.top = (pA.py * 100) + "%";
    cmpDotB.style.left = (pB.px * 100) + "%"; cmpDotB.style.top = (pB.py * 100) + "%";
    cmpTimeLabel.textContent = fmtClock(relMs);
    const deltaMs = pB.tRel - pA.tRel;
    const ahead = deltaMs >= 0 ? styleA : styleB;
    deltaReadout.textContent = ahead.code + " ahead by " + (Math.abs(deltaMs) / 1000).toFixed(3) + "s";
    deltaReadout.style.color = ahead.color;
  }}
  cmpScrubber.addEventListener("input", () => renderCompare(parseFloat(cmpScrubber.value)));

  let cmpPlaying = false, cmpLastFrame = null;
  function cmpTick(ts) {{
    if (!cmpPlaying) return;
    if (cmpLastFrame === null) cmpLastFrame = ts;
    const dt = (ts - cmpLastFrame) * parseFloat(cmpSpeedSel.value);
    cmpLastFrame = ts;
    let v = parseFloat(cmpScrubber.value) + dt;
    if (v > parseFloat(cmpScrubber.max)) v = 0;
    cmpScrubber.value = v;
    renderCompare(v);
    requestAnimationFrame(cmpTick);
  }}
  cmpPlayBtn.addEventListener("click", () => {{
    cmpPlaying = !cmpPlaying;
    cmpPlayBtn.textContent = cmpPlaying ? "Pause" : "Play";
    cmpLastFrame = null;
    if (cmpPlaying) requestAnimationFrame(cmpTick);
  }});

  refreshCompare();
}}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_name", nargs="?", help="Telemetry session name (without _positions.csv)")
    ap.add_argument("--telemetry-dir", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    telemetry_dir = Path(args.telemetry_dir) if args.telemetry_dir else script_dir / "telemetry"

    if args.session_name:
        session_name = args.session_name
    else:
        candidates = sorted(telemetry_dir.glob("*_positions.csv"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise SystemExit(f"No telemetry captures found in {telemetry_dir}. "
                               f"Run live_logger.py during a race first -- this can't replay "
                               f"races that already finished without it running.")
        session_name = candidates[-1].name[: -len("_positions.csv")]

    meta, positions, laps, crashes_csv = load_session(telemetry_dir, session_name)
    if not positions:
        raise SystemExit(f"{session_name} has no recorded positions.")

    server_dir = script_dir.parent
    ac_root = server_dir.parent
    # CSP pads the track string sent over UDP with extra "../" segments for
    # its own online track-checksum scheme (e.g. "csp/3460/../D/../ks_highlands")
    # -- the real on-disk folder is always the last path component, same fix
    # generate_report.py applies to TrackName from the JSON results.
    track_folder = meta["track"].split("/")[-1].strip()
    map_png, map_ini_path = find_map_assets(ac_root, track_folder, meta["track_config"])
    if not map_png:
        raise SystemExit(f"Couldn't find map.png/map.ini for track '{track_folder}' "
                           f"({meta['track_config']}) under {ac_root / 'content' / 'tracks'}")
    map_ini = parse_map_ini(map_ini_path)
    x_off, z_off, scale = map_ini["X_OFFSET"], map_ini["Z_OFFSET"], map_ini["SCALE_FACTOR"]

    from PIL import Image
    with Image.open(map_png) as im:
        img_w, img_h = im.size
        map_b64 = base64.b64encode(map_png.read_bytes()).decode("ascii")

    def to_px_py(x, z):
        return (x + x_off) / scale / img_w, (z + z_off) / scale / img_h

    styles = build_driver_styles(meta)
    car_by_guid = {s["guid"]: cid for cid, s in styles.items()}

    tracks = {}
    raw_tracks = {}
    for p in positions:
        px, py = to_px_py(p["x"], p["z"])
        tracks.setdefault(p["car_id"], []).append({"t": p["t"], "px": px, "py": py, "n": p["n"]})
        raw_tracks.setdefault(p["car_id"], []).append({"t": p["t"], "x": p["x"], "z": p["z"]})
    for pts in tracks.values():
        pts.sort(key=lambda r: r["t"])
    for pts in raw_tracks.values():
        pts.sort(key=lambda r: r["t"])

    max_t = max(p["t"] for p in positions)
    session_start = session_start_datetime(session_name)

    # Opportunistic enrichment from AC's own results JSON + RealPenalty log --
    # neither is guaranteed to exist (test captures, a crashed server before
    # writing results, RealPenalty not running that session, etc).
    laps_df, sector_bests, pit_events = None, None, {}
    results_path = find_results_json(server_dir, session_start, max_t)
    if results_path is not None:
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        if data is not None:
            classification, laps_df, _ = build_tables(data)
            if not classification.empty:
                sector_bests = compute_sector_bests(laps_df, classification)
            penalty_log = find_penalty_log(server_dir, data, results_path)
            if penalty_log is not None:
                pit_events = parse_pit_events(penalty_log, session_start)
            if crashes_csv is None:
                crashes_csv = crashes_from_events(data, car_by_guid, raw_tracks)

    crashes = crashes_csv or []
    for c in crashes:
        c["px"], c["py"] = to_px_py(c["x"], c["z"])

    pits_by_car = {car_by_guid[guid]: v for guid, v in pit_events.items() if guid in car_by_guid}
    lap_timeline = build_lap_timeline(laps, laps_df)
    best_laps = build_best_laps(laps, tracks)

    personal_sectors_by_car, personal_lap_by_car = {}, {}
    overall_sectors, overall_lap = [], None
    if sector_bests:
        overall_sectors = sector_bests.get("overall_sectors") or []
        overall_lap = sector_bests.get("overall_lap")
        for (guid, cid), v in (sector_bests.get("personal_sectors") or {}).items():
            personal_sectors_by_car[cid] = v
        for (guid, cid), v in (sector_bests.get("personal_lap") or {}).items():
            personal_lap_by_car[cid] = v

    drivers_json = [{"carId": cid, "code": s["code"], "color": s["color"], "name": s["name"]}
                      for cid, s in styles.items() if cid in tracks]
    drivers_by_car_id = {str(cid): {"code": s["code"], "color": s["color"], "name": s["name"]}
                           for cid, s in styles.items() if cid in tracks}

    data_json = json.dumps({
        "drivers": drivers_json,
        "driversByCarId": drivers_by_car_id,
        "tracks": {str(k): [{"t": p["t"], "px": p["px"], "py": p["py"]} for p in v]
                    for k, v in tracks.items()},
        "lapTimeline": {str(k): v for k, v in lap_timeline.items()},
        "crashes": [{"t": c["t"], "carId": c["car_id"], "otherCarId": c["other_car_id"], "kind": c["kind"],
                      "speed": c["speed"], "px": c["px"], "py": c["py"], "approx": c.get("approx", False)}
                     for c in crashes],
        "pits": {str(k): v for k, v in pits_by_car.items()},
        "bestLaps": {str(k): v for k, v in best_laps.items()},
        "session": {
            "timeMin": meta.get("session_time_min") or 0,
            "laps": meta.get("session_laps") or 0,
            "overallSectors": overall_sectors,
            "overallLap": overall_lap,
            "personalSectors": {str(k): v for k, v in personal_sectors_by_car.items()},
            "personalLap": {str(k): v for k, v in personal_lap_by_car.items()},
        },
    }, default=_json_default)

    sector_hint = ("Sector splits come from AC's own results JSON for this session "
                    "(purple = overall best, green = personal best)." if sector_bests and overall_sectors
                    else "No matching results JSON found for this session -- sector splits aren't available, "
                          "only lap times.")
    if not meta.get("session_time_min") and not meta.get("session_laps"):
        sector_hint += " (This capture predates session time/laps tracking, so remaining time isn't shown either.)"

    crash_hint = ("Crashes recorded live during capture." if crashes_csv is not None and crashes
                   else "Crash times are approximate -- matched from AC's results JSON against the closest "
                         "recorded position, since this capture predates live crash logging."
                   if crashes else "No crashes recorded for this session.")

    out_path = Path(args.out) if args.out else telemetry_dir / f"{session_name}_replay.html"
    html_out = HTML_TEMPLATE.format(
        title=esc(f"{track_folder} ({meta['track_config']}) — {meta['session_type']} replay"),
        n_drivers=len(drivers_json),
        duration_s=max_t / 1000,
        map_b64=map_b64,
        max_t=max_t,
        data_json=data_json,
        sector_hint=esc(sector_hint),
        crash_hint=esc(crash_hint),
        crash_card_display="block" if crashes else "none",
        compare_disabled="" if len(best_laps) >= 2 else "disabled title=\"Needs at least two drivers with a clean recorded lap\"",
    )
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Replay written to: {out_path}")


if __name__ == "__main__":
    main()
