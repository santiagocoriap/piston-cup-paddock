#!/usr/bin/env python3
"""Generate F1-style race graphics (HTML report + PNG images) from an
Assetto Corsa dedicated server result JSON (server/results/*.json).

Visual language is inspired by MultiViewer's "Race Trace" (the standard
open-source F1 companion tool for this exact chart type: dark surface,
one distinct colour per driver, hover-all-gaps tooltip, click-to-isolate
legend) rather than any copyrighted broadcast graphic -- nothing here is
traced or copied from Formula 1's own graphics package.

Usage:
    python generate_report.py [path/to/result.json] [--out OUTDIR]

If no path is given, the most recent file in ../results is used.
"""
import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.offsetbox import OffsetImage, AnnotationBbox, DrawingArea
import pandas as pd
from PIL import Image

# ---------------------------------------------------------------------------
# Palette -- dark theme (dataviz skill's dark categorical column)
# ---------------------------------------------------------------------------
DRIVER_PALETTE = [
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#e66767",  # red
    "#9085e9",  # violet
    "#4caf4c",  # green (dark-mode legible variant)
]
DASH_MPL = ["-", (0, (5, 2)), (0, (1, 1.5))]      # matplotlib linestyle per cycle
DASH_SVG = [None, "7,3", "1.5,2.5"]                # svg stroke-dasharray per cycle

INK = "#ffffff"            # primary ink (dark surface)
INK2 = "#c3c2b7"           # secondary ink
MUTED = "#898781"          # muted / axis ink
GRID = "#2c2c2a"           # hairline gridline
BASELINE = "#454542"       # axis/baseline
SURFACE = "#1a1a19"        # chart surface
PAGE = "#0d0d0d"           # page plane

TYRE_COLORS = {
    "S": "#e66767", "M": "#c98500", "H": "#9b9b96", "I": "#4caf4c", "W": "#3987e5",
}
TYRE_NAMES = {
    "S": "Soft", "M": "Medium", "H": "Hard", "I": "Intermediate", "W": "Wet",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI Semibold", "Arial", "DejaVu Sans", "sans-serif"],
    "axes.edgecolor": BASELINE,
    "axes.linewidth": 1,
    "grid.color": GRID,
    "grid.linewidth": 1,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "figure.facecolor": PAGE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": PAGE,
    "legend.frameon": False,
})


# ---------------------------------------------------------------------------
# Data loading & derived tables
# ---------------------------------------------------------------------------
def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt_ms(ms):
    if ms is None or ms <= 0 or ms >= 999999999:
        return "—"
    total = ms / 1000
    m = int(total // 60)
    s = total - m * 60
    return f"{m}:{s:06.3f}" if m else f"{s:.3f}"


def fmt_gap(ms):
    return "—" if ms <= 0 else f"+{ms / 1000:.3f}"


def track_title(data):
    track = data.get("TrackName", "") or ""
    track = track.split("/")[-1].replace("_", " ").strip().title()
    cfg = (data.get("TrackConfig") or "").replace("_", " ").strip()
    return f"{track} ({cfg.title()})" if cfg else track


def track_folder_and_config(data):
    """Raw (non-prettified) folder/config names, as used on disk under content/tracks."""
    folder = (data.get("TrackName", "") or "").split("/")[-1].strip()
    config = (data.get("TrackConfig") or "").strip()
    return folder, config


def short_name(name, n=18):
    name = (name or "").strip()
    return name if len(name) <= n else name[: n - 1] + "…"


def safe_asset_name(s):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in (s or ""))[:80]


def build_tables(data):
    result = data.get("Result", [])
    laps_raw = data.get("Laps", [])
    skin_by_car_id = {c["CarId"]: c.get("Skin", "") for c in data.get("Cars", [])}

    lap_counts = {}
    clean_laps = {}
    for l in laps_raw:
        key = (l["DriverGuid"], l["CarId"])
        lap_counts[key] = lap_counts.get(key, 0) + 1
        if l.get("Cuts", 0) == 0 and l.get("LapTime", 0) > 0:
            clean_laps.setdefault(key, []).append(l["LapTime"])

    rows = []
    for i, r in enumerate(result):
        key = (r["DriverGuid"], r["CarId"])
        clean = clean_laps.get(key) or []
        rows.append({
            "pos": i + 1,
            "driver": r["DriverName"],
            "guid": r["DriverGuid"],
            "car_id": r["CarId"],
            "car": r.get("CarModel", ""),
            "skin": skin_by_car_id.get(r["CarId"], ""),
            "best_lap_ms": r.get("BestLap", 0),
            "avg_clean_ms": round(sum(clean) / len(clean)) if clean else 0,
            "total_ms": r.get("TotalTime", 0),
            "laps": lap_counts.get(key, 0),
            "finished": (r.get("TotalTime", 0) or 0) > 0,
        })
    classification = pd.DataFrame(rows)
    if classification.empty:
        return classification, pd.DataFrame(laps_raw), 0

    # A player who rejoined or swapped cars shows up as a second Result
    # entry under the same GUID with a different CarId -- same driver, not
    # a separate competitor. Keep whichever entry actually has lap data.
    classification = (classification.sort_values("laps", ascending=False)
                        .drop_duplicates(subset="guid", keep="first"))

    # A car with zero recorded laps never actually started (DNS), it isn't
    # a DNF, and it has nothing to plot anywhere -- drop it from the report
    # entirely rather than mislabel and clutter every chart with it.
    classification = classification[classification["laps"] > 0].copy()

    # Original Result[] order is already the correct finishing order; after
    # dropping duplicates/DNS, renumber positions so there are no gaps.
    classification = classification.sort_values("pos").reset_index(drop=True)
    classification["pos"] = classification.index + 1

    max_laps = int(classification["laps"].max()) if not classification.empty else 0
    leader_time = classification.iloc[0]["total_ms"] if not classification.empty else 0

    def make_gap(row):
        if not row["finished"]:
            return "DNF"
        if row["pos"] == 1:
            return "Leader"
        if row["laps"] < max_laps:
            down = max_laps - row["laps"]
            return f"+{down} Lap" + ("s" if down > 1 else "")
        return fmt_gap(row["total_ms"] - leader_time)

    classification["gap"] = classification.apply(make_gap, axis=1)

    kept_keys = set(zip(classification["guid"], classification["car_id"]))
    laps_df = pd.DataFrame(laps_raw)
    if not laps_df.empty:
        laps_df["key"] = list(zip(laps_df["DriverGuid"], laps_df["CarId"]))
        laps_df = laps_df[laps_df["key"].isin(kept_keys)]
        laps_df = laps_df.sort_values(["DriverGuid", "CarId", "Timestamp"])
        laps_df["lap_number"] = laps_df.groupby(["DriverGuid", "CarId"]).cumcount() + 1

    return classification, laps_df, max_laps


def compute_positions(laps_df):
    if laps_df.empty:
        return laps_df
    pos_df = laps_df.copy()
    pos_df["position"] = pos_df.groupby("lap_number")["Timestamp"].rank(method="first").astype(int)
    leader_time = pos_df.groupby("lap_number")["Timestamp"].transform("min")
    pos_df["gap_s"] = (pos_df["Timestamp"] - leader_time) / 1000.0
    return pos_df


def driver_code(name, used):
    letters = re.sub(r"[^A-Za-z]", "", name or "").upper()
    base = (letters[:3] or "DRV").ljust(3, "X")
    code, n = base, 1
    while code in used:
        n += 1
        code = base[:2] + str(n)
    used.add(code)
    return code


def driver_styles(classification):
    """One style (color, dash, 3-letter code) per driver, assigned in
    finishing-position order so P1 always gets palette slot 1, etc."""
    styles = {}
    used_codes = set()
    # Only drivers who actually set a lap get a cycling palette slot (they're
    # the ones who can appear on a line chart); DNFs with zero laps never
    # plot a line, so give them a flat neutral chip instead of wrapping back
    # into the palette and colliding with an early finisher's colour.
    i = 0
    for _, row in classification.sort_values("pos").iterrows():
        key = (row["guid"], row["car_id"])
        has_laps = row["laps"] > 0
        if has_laps:
            cycle, slot = divmod(i, len(DRIVER_PALETTE))
            color = DRIVER_PALETTE[slot]
            dash_mpl = DASH_MPL[min(cycle, len(DASH_MPL) - 1)]
            dash_svg = DASH_SVG[min(cycle, len(DASH_SVG) - 1)]
            i += 1
        else:
            color, dash_mpl, dash_svg = MUTED, "-", None
        styles[key] = {
            "color": color,
            "dash_mpl": dash_mpl,
            "dash_svg": dash_svg,
            "code": driver_code(row["driver"], used_codes),
            "label": short_name(row["driver"]),
            "pos": row["pos"],
        }
    return styles


# ---------------------------------------------------------------------------
# Game content assets -- car preview photos and the track's own minimap
# outline, pulled straight from the local AC install.
# ---------------------------------------------------------------------------
def find_car_preview(ac_root, car_model, skin):
    if not car_model or not skin:
        return None
    p = ac_root / "content" / "cars" / car_model / "skins" / skin / "preview.jpg"
    return p if p.exists() else None


def find_track_outline(ac_root, folder, config):
    base = ac_root / "content" / "tracks" / folder
    candidates = []
    if config:
        candidates.append(base / "ui" / config / "outline.png")
    candidates.append(base / "ui" / "outline.png")
    ui_dir = base / "ui"
    if ui_dir.exists():
        candidates.extend(sorted(ui_dir.glob("*/outline.png")))
    for c in candidates:
        if c.exists():
            return c
    return None


def find_track_map(ac_root, folder, config):
    """The track's own GPS/radar map -- a clean vector-style ribbon AC
    renders in the driving HUD. Unlike ui/outline.png and ui/preview.png
    (cosmetic, mod-author-supplied, often shipped tiny), this asset is
    required for gameplay (AI line + HUD), so it's reliably sharp."""
    base = ac_root / "content" / "tracks" / folder
    candidates = []
    if config:
        candidates.append(base / config / "map.png")
    candidates.append(base / "map.png")
    if base.exists():
        candidates.extend(sorted(base.glob("*/map.png")))
    for c in candidates:
        if c.exists():
            return c
    return None


def find_track_preview(ac_root, folder, config):
    base = ac_root / "content" / "tracks" / folder / "ui"
    candidates = []
    if config:
        candidates.append(base / config / "preview.png")
    candidates.append(base / "preview.png")
    if base.exists():
        candidates.extend(sorted(base.glob("*/preview.png")))
    for c in candidates:
        if c.exists():
            return c
    return None


def find_car_badge(ac_root, car_model):
    p = ac_root / "content" / "cars" / car_model / "ui" / "badge.png"
    return p if p.exists() else None


def find_track_meta(ac_root, folder, config):
    base = ac_root / "content" / "tracks" / folder / "ui"
    candidates = []
    if config:
        candidates.append(base / config / "ui_track.json")
    candidates.append(base / "ui_track.json")
    if base.exists():
        candidates.extend(sorted(base.glob("*/ui_track.json")))
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                continue
    return None


_PENALTY_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+):")


def find_penalty_log(server_dir, data, result_path):
    """The RealPenalty plugin (server/realpenalty) keeps a separate,
    much richer event log per session -- cutting warnings, penalties
    issued/served, final time penalties -- than anything in the AC
    server's own results JSON. There's no shared session ID between the
    two, so match on timing: the result JSON is written the instant the
    session ends, which is also (usually, to the microsecond) the last
    logged line in the matching penalty log.

    "Usually" because a quiet closing stretch with no cuts, pits or
    warnings means nothing gets logged near the actual end, so the last
    line can trail the result's mtime by minutes rather than
    microseconds -- hence the generous MAX_GAP_BEFORE below. The two
    sides aren't symmetric, though: the AC server sometimes starts the
    *next* session (and RealPenalty a fresh stub log for it) within
    moments of writing this result, so a candidate whose last line
    lands meaningfully after the target is almost always that next
    session's log, not this one -- only a tiny clock-skew grace is
    allowed on that side."""
    session_type = (data.get("Type") or "").strip().lower()
    if not session_type:
        return None
    logs_dir = server_dir / "realpenalty" / "logs"
    candidates = sorted(logs_dir.glob(f"{session_type}_penalty_*.log"))
    if not candidates:
        return None
    try:
        target = result_path.stat().st_mtime
    except OSError:
        return None

    GRACE_AFTER = 5       # clock-skew allowance for a last line landing a hair after the target
    MAX_GAP_BEFORE = 600  # quiet-ending allowance for a last line landing well before the target

    best, best_last = None, None
    for c in candidates:
        try:
            lines = c.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        last_ts = None
        for line in reversed(lines):
            m = _PENALTY_LOG_TS_RE.match(line)
            if m:
                try:
                    last_ts = datetime.fromisoformat(m.group(1)).timestamp()
                except ValueError:
                    pass
                break
        if last_ts is None:
            continue
        if last_ts > target + GRACE_AFTER or target - last_ts > MAX_GAP_BEFORE:
            continue
        if best_last is None or last_ts > best_last:
            best, best_last = c, last_ts
    return best


_WARNING_RE = re.compile(r"Cutting Warning - Car ID: \d+ - Name: .*? - GUID: (\d+) - Lap: (\d+)")
_NEW_PENALTY_RE = re.compile(
    r"New penalty - Car ID: \d+ - Name: .*? - GUID: (\d+) - Penalty: (.*?) - Cause: (\w+) - "
    r"Other: (\[.*?\]) - Lap: (\d+) - Laps left: \S+ - ID: (\d+)"
)
_PENALTY_TAKEN_RE = re.compile(
    r"Penalty Taken - Car ID: \d+ - Name: .*? - GUID: (\d+) - Penalty: .*? - Lap: (\d+) - ID: (\d+)"
)
_PENALTY_WRONG_RE = re.compile(
    r"Penalty wrong taken - Car ID: \d+ - Name: .*? - GUID: (\d+) - Penalty: .*? - pit - Lap: (\d+) - ID: (\d+)"
)
_FINAL_TIME_PENALTY_RE = re.compile(
    r"Seconds penalty to final time - Car ID: \d+ - Name: .*? - GUID: (\d+) - Team:.*? - seconds: (\d+)"
)


def parse_penalty_log(path):
    """Returns {guid: {"warnings": int, "warning_laps": [int], "penalties": [...],
    "time_penalty_s": int}}."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    incidents = {}

    def bucket(guid):
        return incidents.setdefault(
            guid, {"warnings": 0, "warning_laps": [], "penalties": {}, "time_penalty_s": 0})

    for line in text.splitlines():
        m = _WARNING_RE.search(line)
        if m:
            guid, lap = m.groups()
            b = bucket(guid)
            b["warnings"] += 1
            b["warning_laps"].append(int(lap))
            continue
        m = _NEW_PENALTY_RE.search(line)
        if m:
            guid, ptype, cause, other, lap, pid = m.groups()
            extra = cause
            if cause in ("speed", "jump") and other not in ("[]", ""):
                strip_chars = "[]" + "'"
                extra = f"{cause} {other.strip(strip_chars)}"
            bucket(guid)["penalties"][pid] = {"type": ptype, "cause": extra, "lap": lap, "status": "issued"}
            continue
        m = _PENALTY_TAKEN_RE.search(line)
        if m:
            guid, lap, pid = m.groups()
            p = bucket(guid)["penalties"].get(pid)
            if p:
                p["status"] = "served"
            continue
        m = _PENALTY_WRONG_RE.search(line)
        if m:
            guid, lap, pid = m.groups()
            p = bucket(guid)["penalties"].get(pid)
            if p and p["status"] != "served":
                p["status"] = "wrong attempt"
            continue
        m = _FINAL_TIME_PENALTY_RE.search(line)
        if m:
            guid, secs = m.groups()
            bucket(guid)["time_penalty_s"] += int(secs)

    for v in incidents.values():
        v["penalties"] = list(v["penalties"].values())
    return incidents


_PIT_ENTER_RE = re.compile(r"Pit lane entered - Car: \d+ - Driver: .*? - GUID: (\d+) - Correct way: \w+ - lap: (\d+)")
_PIT_STOP_RE = re.compile(r"Pit stop - Car: \d+ - Driver: .*? - GUID: (\d+) - Model:")
_PIT_LEFT_RE = re.compile(r"Pit lane left - Car: \d+ - Driver: .*? - GUID: (\d+) - lap: (\d+) - Tyres:")


def build_pit_stops(path):
    """Genuine box stops only -- a drive-through penalty also logs 'Pit lane
    entered'/'Pit lane left' but never a 'Pit stop' line in between, so it's
    naturally excluded. Returns {guid: [{"in_lap": int, "out_lap": int|None}]}."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    pending = {}
    stops = {}
    for line in text.splitlines():
        m = _PIT_ENTER_RE.search(line)
        if m:
            guid, lap = m.groups()
            pending[guid] = {"in_lap": int(lap), "stopped": False}
            continue
        m = _PIT_STOP_RE.search(line)
        if m:
            p = pending.get(m.group(1))
            if p:
                p["stopped"] = True
            continue
        m = _PIT_LEFT_RE.search(line)
        if m:
            guid, lap = m.groups()
            p = pending.pop(guid, None)
            if p and p["stopped"]:
                stops.setdefault(guid, []).append({"in_lap": p["in_lap"], "out_lap": int(lap)})
            continue
    for guid, p in pending.items():
        if p["stopped"]:
            stops.setdefault(guid, []).append({"in_lap": p["in_lap"], "out_lap": None})
    return stops


def build_crash_stats(data):
    """The AC server's own results JSON logs every collision natively under
    "Events" -- no RealPenalty log needed for this one. Keyed by GUID
    (not CarId) since that's what each event carries directly.

    Events carry no timestamp or lap number, so there's no reliable way to
    tell a crash during the race from one after it. What IS reliable: a
    run of consecutive events for the same driver, same type, same exact
    position is a car stuck overlapping something re-triggering the same
    contact every tick, not repeated distinct impacts -- so those are
    collapsed into one before counting."""
    stats = {}
    last_sig = None
    for e in data.get("Events", []):
        guid = (e.get("Driver") or {}).get("Guid")
        etype = e.get("Type")
        if not guid or etype not in ("COLLISION_WITH_CAR", "COLLISION_WITH_ENV"):
            last_sig = None
            continue
        wp = e.get("WorldPosition") or {}
        pos = (round(wp.get("X", 0), 1), round(wp.get("Y", 0), 1), round(wp.get("Z", 0), 1))
        sig = (guid, etype, pos)
        if sig == last_sig:
            continue
        last_sig = sig
        s = stats.setdefault(guid, {"car": 0, "env": 0, "max_speed": 0.0})
        s["car" if etype == "COLLISION_WITH_CAR" else "env"] += 1
        speed = e.get("ImpactSpeed") or 0
        if speed > s["max_speed"]:
            s["max_speed"] = speed
    return stats


def prepare_assets(ac_root, classification, styles, folder, config, out_dir):
    """Copy/derive small local assets into out_dir/assets so the report is
    self-contained: resized driver-car thumbnails, manufacturer badges, a
    white-recoloured track outline, and a darkened aerial preview for the
    header backdrop. Returns (car_thumbs, badges, outline_rel, preview_rel, meta)."""
    assets_dir = out_dir / "assets"
    cars_dir = assets_dir / "cars"
    badges_dir = assets_dir / "badges"
    cars_dir.mkdir(parents=True, exist_ok=True)
    badges_dir.mkdir(parents=True, exist_ok=True)

    car_thumbs = {}
    badges = {}
    for _, row in classification.iterrows():
        key = (row["guid"], row["car_id"])
        src = find_car_preview(ac_root, row["car"], row.get("skin", ""))
        if src:
            code = styles[key]["code"]
            dest = cars_dir / f"{code}.jpg"
            try:
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    im.thumbnail((240, 135))
                    im.save(dest, "JPEG", quality=82)
                car_thumbs[key] = f"assets/cars/{code}.jpg"
            except OSError:
                pass

        if row["car"] and row["car"] not in badges:
            badge_src = find_car_badge(ac_root, row["car"])
            if badge_src:
                dest = badges_dir / f"{safe_asset_name(row['car'])}.png"
                try:
                    with Image.open(badge_src) as im:
                        im = im.convert("RGBA")
                        im.thumbnail((64, 64))
                        im.save(dest, "PNG")
                    badges[row["car"]] = f"assets/badges/{safe_asset_name(row['car'])}.png"
                except OSError:
                    pass

    # The GPS/radar map AC itself draws in the driving HUD: required for
    # gameplay (the AI line + on-screen map), so unlike ui/outline.png and
    # ui/preview.png -- cosmetic extras a mod author may ship tiny or skip
    # polishing -- it's reliably present and properly anti-aliased. Prefer
    # it over ui/outline.png for the circuit card; fall back if a mod is
    # missing it.
    outline_rel = None
    outline_src = find_track_map(ac_root, folder, config) or find_track_outline(ac_root, folder, config)
    if outline_src:
        try:
            with Image.open(outline_src) as im:
                im = im.convert("RGBA")
                # map.png ships on a huge transparent canvas sized for the
                # track's real-world extent -- crop to the drawn content
                # (plus a little breathing room) instead of a sea of padding.
                bbox = im.getchannel("A").getbbox()
                if bbox:
                    pad = round(max(im.size) * 0.03)
                    l, t, r, b = bbox
                    im = im.crop((max(0, l - pad), max(0, t - pad),
                                   min(im.width, r + pad), min(im.height, b + pad)))
                # Real tracks are tall as often as they're wide. Rotate
                # portrait layouts to landscape so every track renders into
                # the same fixed-size box in the circuit card instead of
                # some tracks stretching the card tall and others not.
                if im.height > im.width:
                    im = im.transpose(Image.ROTATE_90)
                # Some mods' ui/outline.png fallback ships very small (~350x200)
                # -- thumbnail() only ever shrinks, so a source already under
                # the cap passed through untouched and its hard, low-res edges
                # showed up as jagged stair-stepping once displayed larger.
                # Upscale with a smooth filter first so the resample itself
                # manufactures anti-aliasing the source never had.
                if im.width < 1200:
                    scale = 1200 / im.width
                    im = im.resize((1200, round(im.height * scale)), Image.LANCZOS)
                im.thumbnail((1200, 1200), Image.LANCZOS)
                # Recolour the line art to a light, theme-matching tint while
                # keeping its alpha mask, so it reads on the dark surface
                # regardless of the source line colour.
                tint = Image.new("RGBA", im.size, (195, 194, 183, 255))
                tint.putalpha(im.getchannel("A"))
                tint.save(assets_dir / "track_outline.png", "PNG")
            outline_rel = "assets/track_outline.png"
        except OSError:
            outline_rel = None

    # The aerial preview photo's resolution is entirely up to the mod author
    # (seen anywhere from 355x200 to 1920x1080) -- stretching a low-res one
    # across the full-width hero banner is what caused the pixelation.
    # Below this floor the upscale is too large to hide convincingly even
    # with a blur, so skip the photo rather than ship a blurry one: the hero
    # falls back to a graphic treatment built from the sharp map outline
    # above, which always looks crisp because it's never a stretched photo.
    MIN_SHARP_PREVIEW_WIDTH = 900
    preview_rel = None
    preview_src = find_track_preview(ac_root, folder, config)
    if preview_src:
        try:
            with Image.open(preview_src) as im:
                im = im.convert("RGB")
                if im.width >= MIN_SHARP_PREVIEW_WIDTH:
                    # Already sharp at banner width -- resize if oversized,
                    # darken gently, no blur needed to hide anything.
                    im.thumbnail((1920, 1920), Image.LANCZOS)
                    import numpy as np
                    arr = (np.asarray(im).astype("float32") * 0.7).astype("uint8")
                    Image.fromarray(arr).save(assets_dir / "track_preview.jpg", "JPEG", quality=90)
                    preview_rel = "assets/track_preview.jpg"
        except OSError:
            preview_rel = None

    meta = find_track_meta(ac_root, folder, config)
    return car_thumbs, badges, outline_rel, preview_rel, meta


RIM_COLOR = "#9b9b96"
TYRE_BODY_COLOR = "#161616"


def _tyre_icon_drawing_area(color, size=16):
    """A small drawn tyre icon -- black tread, a thin coloured sidewall
    stripe (how real tyre compounds are actually marked), a silver rim and
    a dark hub -- so it reads as a tyre, not a flat colour swatch."""
    c = size / 2
    r = c - 1
    da = DrawingArea(size, size, 0, 0)
    da.add_artist(patches.Circle((c, c), r, facecolor=TYRE_BODY_COLOR, edgecolor=BASELINE, linewidth=0.8))
    da.add_artist(patches.Circle((c, c), r * 0.8, facecolor=color, edgecolor="none"))
    da.add_artist(patches.Circle((c, c), r * 0.68, facecolor=TYRE_BODY_COLOR, edgecolor="none"))
    da.add_artist(patches.Circle((c, c), r * 0.42, facecolor=RIM_COLOR, edgecolor="none"))
    da.add_artist(patches.Circle((c, c), r * 0.14, facecolor=TYRE_BODY_COLOR, edgecolor="none"))
    return da


def tyre_icon_svg(color, size=20):
    r = size / 2
    body = r - 1
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="flex-shrink:0;width:{size}px;height:{size}px">'
        f'<circle cx="{r}" cy="{r}" r="{body:.1f}" fill="{TYRE_BODY_COLOR}" stroke="var(--baseline)" stroke-width="1"/>'
        f'<circle cx="{r}" cy="{r}" r="{body * 0.8:.1f}" fill="{color}"/>'
        f'<circle cx="{r}" cy="{r}" r="{body * 0.68:.1f}" fill="{TYRE_BODY_COLOR}"/>'
        f'<circle cx="{r}" cy="{r}" r="{body * 0.42:.1f}" fill="{RIM_COLOR}"/>'
        f'<circle cx="{r}" cy="{r}" r="{body * 0.14:.1f}" fill="{TYRE_BODY_COLOR}"/>'
        f'</svg>'
    )


def compute_sector_bests(laps_df, classification):
    """Overall-best and per-driver personal-best for each sector index and
    for the whole lap, used to colour the timing sheet purple/green."""
    if laps_df.empty or "Sectors" not in laps_df.columns:
        return {"overall_sectors": [], "overall_lap": None, "personal_sectors": {}, "personal_lap": {}}
    n_sectors = max((len(s) for s in laps_df["Sectors"] if isinstance(s, list)), default=0)
    overall_sectors = [None] * n_sectors
    personal_sectors = {}
    personal_lap = {}
    for _, row in laps_df.iterrows():
        key = row["key"]
        sectors = row.get("Sectors") or []
        for i, v in enumerate(sectors):
            if v and v > 0:
                if overall_sectors[i] is None or v < overall_sectors[i]:
                    overall_sectors[i] = v
                pb = personal_sectors.setdefault(key, [None] * n_sectors)
                if pb[i] is None or v < pb[i]:
                    pb[i] = v
        lt = row.get("LapTime")
        if lt and lt > 0:
            if lt < personal_lap.get(key, float("inf")):
                personal_lap[key] = lt
    valid_laps = laps_df[laps_df["LapTime"] > 0]["LapTime"]
    overall_lap = valid_laps.min() if not valid_laps.empty else None
    return {
        "overall_sectors": overall_sectors,
        "overall_lap": overall_lap,
        "personal_sectors": personal_sectors,
        "personal_lap": personal_lap,
    }


# ---------------------------------------------------------------------------
# PNG rendering
# ---------------------------------------------------------------------------
def style_axes(ax, y_grid=True):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(BASELINE)
    ax.tick_params(colors=INK2, labelsize=9)
    if y_grid:
        ax.yaxis.grid(True, linewidth=1, color=GRID)
        ax.set_axisbelow(True)
    ax.xaxis.grid(False)


def _hex_to_rgba(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def _place_image(ax, path, x, y, zoom, zorder=8, bg=None):
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            if bg:
                # Flatten transparency onto the given background color --
                # Image.convert("RGB") alone would just drop the alpha
                # channel and keep whatever RGB was stored under it, which
                # for a flat-tinted line-art PNG renders as a solid block.
                backdrop = Image.new("RGBA", im.size, _hex_to_rgba(bg))
                im = Image.alpha_composite(backdrop, im)
            import numpy as np
            box = OffsetImage(np.asarray(im.convert("RGB")), zoom=zoom)
            box.image.axes = ax
            ab = AnnotationBbox(box, (x, y), frameon=False, zorder=zorder, pad=0)
            ax.add_artist(ab)
            return True
    except OSError:
        return False


def render_podium_png(classification, title, out_path, car_thumbs=None, outline_path=None):
    car_thumbs = car_thumbs or {}
    styles = driver_styles(classification)
    fig = plt.figure(figsize=(8, 11.2), dpi=200)
    fig.patch.set_facecolor(PAGE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14.2)
    ax.axis("off")
    ax.add_patch(patches.Rectangle((0, 0), 10, 14.2, facecolor=SURFACE, edgecolor="none"))

    if outline_path:
        _place_image(ax, outline_path, 8.3, 13.2, zoom=0.16, zorder=1, bg=SURFACE)

    ax.text(0.6, 13.6, title.upper(), ha="left", va="top", fontsize=16, color=INK,
             fontweight="black", family="sans-serif", zorder=2)
    ax.text(0.6, 13.05, "RACE RESULT", ha="left", va="top", fontsize=10, color=MUTED,
             fontweight="bold", zorder=2)
    ax.plot([0.6, 9.4], [12.75, 12.75], color=DRIVER_PALETTE[0], linewidth=3, solid_capstyle="round", zorder=2)

    heights = [2.6, 3.4, 2.1]
    xs = [1.2, 4.0, 6.8]
    order = [1, 0, 2]  # P2, P1, P3 left-to-right
    base_y = 11.6
    for rank_idx in order:
        if rank_idx >= len(classification):
            continue
        row = classification.iloc[rank_idx]
        key = (row["guid"], row["car_id"])
        h = heights[rank_idx]
        x = xs[order.index(rank_idx)]
        color = styles[key]["color"]
        thumb = car_thumbs.get(key)
        if thumb:
            _place_image(ax, thumb, x + 1.0, base_y + 1.0, zoom=0.17)
        ax.add_patch(patches.Rectangle((x, base_y - h), 2.0, h, facecolor=color, edgecolor="none"))
        ax.text(x + 1.0, base_y + 0.35, f"P{rank_idx + 1}", ha="center", va="bottom",
                fontsize=14, color=INK, fontweight="black")
        ax.text(x + 1.0, base_y - 0.25, short_name(row["driver"], 16), ha="center", va="top",
                fontsize=10.5, color=PAGE, fontweight="bold")
        ax.text(x + 1.0, base_y - h + 0.3, fmt_ms(row["best_lap_ms"]), ha="center", va="bottom",
                fontsize=8.5, color=PAGE, fontweight="bold")

    # full classification table (text block, table view)
    y = base_y - max(heights) - 0.9
    ax.text(0.6, y, "POS", fontsize=8.5, color=MUTED, fontweight="bold")
    ax.text(2.6, y, "DRIVER", fontsize=8.5, color=MUTED, fontweight="bold")
    ax.text(6.6, y, "GAP", fontsize=8.5, color=MUTED, fontweight="bold")
    ax.text(8.6, y, "BEST", fontsize=8.5, color=MUTED, fontweight="bold")
    y -= 0.35
    ax.plot([0.6, 9.4], [y + 0.12, y + 0.12], color=BASELINE, linewidth=1)
    for _, row in classification.iterrows():
        y -= 0.5
        if y < 0.35:
            break
        key = (row["guid"], row["car_id"])
        s = styles[key]
        thumb = car_thumbs.get(key)
        if thumb:
            _place_image(ax, thumb, 1.55, y + 0.05, zoom=0.1)
        ax.add_patch(patches.Rectangle((0.55, y - 0.14), 0.32, 0.32, facecolor=s["color"], edgecolor="none"))
        ax.text(0.71, y + 0.02, str(row["pos"]), fontsize=8.5, color=PAGE, fontweight="black", ha="center", va="center")
        ax.text(2.6, y, short_name(row["driver"], 20), fontsize=9.5, color=INK)
        ax.text(6.6, y, row["gap"], fontsize=9.5, color=INK2)
        ax.text(8.6, y, fmt_ms(row["best_lap_ms"]), fontsize=9, color=INK2)

    fig.savefig(out_path, facecolor=PAGE)
    plt.close(fig)


def render_line_chart_png(laps_df, classification, value_col, title, ylabel, out_path,
                            invert_y=False, min_zero=False):
    styles = driver_styles(classification)
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    fig.patch.set_facecolor(PAGE)
    style_axes(ax)

    all_values = []
    end_labels = []  # deferred until axis limits are final, to declutter in pixel space
    for _, row in classification.sort_values("pos").iterrows():
        key = (row["guid"], row["car_id"])
        g = laps_df[laps_df["key"] == key].sort_values("lap_number")
        if g.empty:
            continue
        s = styles[key]
        ax.plot(g["lap_number"], g[value_col], color=s["color"], linewidth=2,
                 linestyle=s["dash_mpl"], label=f'{s["code"]} {s["label"]}', zorder=3)
        last = g.iloc[-1]
        ax.scatter([last["lap_number"]], [last[value_col]], s=22, color=s["color"],
                    edgecolor=SURFACE, linewidth=1.5, zorder=4)
        end_labels.append({"x": last["lap_number"], "y": last[value_col],
                             "code": s["code"], "color": s["color"]})
        all_values.extend(g[value_col].tolist())

    # Robust axis range: 3rd-97th percentile of everyone, so a long pit stop
    # or a disconnect doesn't flatten the whole field's battle -- that line
    # simply exits the frame at the top, same as a broadcast graphic crops it.
    if not invert_y and all_values:
        s_vals = sorted(all_values)
        n = len(s_vals)
        lo = s_vals[max(0, int(n * 0.03))]
        hi = s_vals[min(n - 1, int(n * 0.97))]
        pad = (hi - lo) * 0.25 or hi * 0.1 or 1
        ymin = (lo - pad)
        if min_zero:
            ymin = max(0, ymin)
        ax.set_ylim(ymin, hi + pad)

    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.1), ncol=4, fontsize=8.5,
               handlelength=1.6, labelcolor=INK2)
    ax.set_title(title, fontsize=14, color=INK, fontweight="black", loc="left", pad=14)
    ax.set_xlabel("Lap", fontsize=9.5)
    ax.set_ylabel(ylabel, fontsize=9.5)
    if invert_y:
        ax.invert_yaxis()
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    else:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}s"))
    fig.tight_layout()

    # Declutter end-of-line driver-code labels in pixel space so close
    # finishers don't print on top of each other.
    if end_labels:
        fig.canvas.draw()
        pts = sorted(end_labels, key=lambda ls: ax.transData.transform((ls["x"], ls["y"]))[1])
        px_y = [ax.transData.transform((p["x"], p["y"]))[1] for p in pts]
        min_gap = 13
        for i in range(1, len(px_y)):
            if px_y[i] - px_y[i - 1] < min_gap:
                px_y[i] = px_y[i - 1] + min_gap
        for ls, yy in zip(pts, px_y):
            x_px = ax.transData.transform((ls["x"], ls["y"]))[0]
            x_data, y_data = ax.transData.inverted().transform((x_px + 8, yy))
            ax.text(x_data, y_data, ls["code"], fontsize=7.5, color=ls["color"],
                     fontweight="bold", va="center", clip_on=False)

    fig.savefig(out_path, facecolor=PAGE)
    plt.close(fig)


def render_tyre_strategy_png(laps_df, classification, title, out_path):
    """Each lap gets its own cell (not one solid stint block) so the chart
    actually shows lap count and exactly where a tyre change happened."""
    styles = driver_styles(classification)
    drivers = [(row["guid"], row["car_id"]) for _, row in classification.sort_values("pos").iterrows()
                if (row["guid"], row["car_id"]) in set(laps_df["key"])] if not laps_df.empty else []
    n = len(drivers)
    if n == 0:
        return
    max_lap = int(laps_df["lap_number"].max())

    fig, ax = plt.subplots(figsize=(max(9.5, max_lap * 0.4), 0.42 * n + 1.8), dpi=200)
    fig.patch.set_facecolor(PAGE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor(SURFACE)

    seen_tyres = set()
    for i, key in enumerate(drivers):
        y = n - i - 1
        s = styles.get(key, {"code": "???", "color": MUTED})
        g = laps_df[laps_df["key"] == key].sort_values("lap_number")
        for _, lap in g.iterrows():
            tyre = lap.get("Tyre") or "?"
            color = TYRE_COLORS.get(tyre, MUTED)
            ax.barh(y, 0.86, left=lap["lap_number"] - 1, height=0.62, color=color)
            seen_tyres.add(tyre)
        ax.text(-0.6, y, s["code"], ha="right", va="center", fontsize=9.5, color=s["color"], fontweight="bold")

    ax.set_yticks([])
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(-0.3, max_lap + 0.3)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=min(max_lap, 20)))
    ax.xaxis.grid(True, linewidth=1, color=GRID)
    ax.set_axisbelow(True)
    ax.set_xlabel("Lap", fontsize=9.5)
    ax.set_title(title, fontsize=14, color=INK, fontweight="black", loc="left", pad=14)

    fig.tight_layout()
    legend_y = -0.09 * (18 / max(n, 6))
    x0 = 0.0
    for t in sorted(seen_tyres):
        da = _tyre_icon_drawing_area(TYRE_COLORS.get(t, MUTED), size=15)
        ab = AnnotationBbox(da, (x0, legend_y), xycoords="axes fraction", frameon=False,
                              box_alignment=(0, 0.5))
        ax.add_artist(ab)
        ax.annotate(TYRE_NAMES.get(t, t), xy=(x0 + 0.028, legend_y), xycoords="axes fraction",
                     va="center", ha="left", color=INK2, fontsize=9)
        x0 += 0.16
    # bbox_inches="tight" so the legend row added after tight_layout() --
    # which sits below the axes in negative-fraction space -- doesn't get
    # cropped off by the figure's original saved bounds.
    fig.savefig(out_path, facecolor=PAGE, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)


# ---------------------------------------------------------------------------
# HTML report (inline SVG + hover crosshair + click-to-isolate legend)
# ---------------------------------------------------------------------------
def esc(s):
    return html.escape(str(s))


def chart_series_json(laps_df, classification, value_col):
    styles = driver_styles(classification)
    max_lap = int(laps_df["lap_number"].max()) if not laps_df.empty else 0
    series = []
    for _, row in classification.sort_values("pos").iterrows():
        key = (row["guid"], row["car_id"])
        g = laps_df[laps_df["key"] == key].sort_values("lap_number")
        if g.empty:
            continue
        s = styles[key]
        values = [None] * max_lap
        for _, r in g.iterrows():
            values[int(r["lap_number"]) - 1] = round(float(r[value_col]), 3)
        series.append({"code": s["code"], "label": s["label"], "color": s["color"],
                        "dash": s["dash_svg"], "pos": int(s["pos"]), "values": values})
    return {"maxLap": max_lap, "series": series}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<title>{title} — Race Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Titillium+Web:wght@600;700;900&display=swap" rel="stylesheet">
<style>
  @media (prefers-reduced-motion: no-preference) {{
    .hero-sweep {{ transform: translateX(120%); animation: sweepIn .9s cubic-bezier(.22,.8,.2,1) .05s forwards; }}
    .session-badge {{ opacity: 0; transform: scale(.82); animation: badgePop .4s cubic-bezier(.34,1.56,.64,1) .15s forwards; }}
    .hero-title {{ clip-path: inset(0 100% 0 0); animation: titleWipe .65s cubic-bezier(.3,.82,.2,1) .25s forwards; }}
    .hero-sub {{ opacity: 0; transform: translateY(6px); animation: riseIn .5s ease .55s forwards; }}
    .podium-box {{ transform: scaleY(0); animation: growUp .55s cubic-bezier(.22,.9,.3,1) forwards; }}
    .tyre-bars {{ transform: scaleX(0); animation: wipeIn .5s cubic-bezier(.3,.8,.2,1) forwards; }}
    .timing-table td.purple {{ animation: pulseGlow 1.6s ease-out 1.2s 2; }}
  }}
  @keyframes sweepIn {{ to {{ transform: translateX(0); }} }}
  @keyframes badgePop {{ to {{ opacity: 1; transform: scale(1); }} }}
  @keyframes titleWipe {{ to {{ clip-path: inset(0 0 0 0); }} }}
  @keyframes riseIn {{ to {{ opacity: 1; transform: translateY(0); }} }}
  @keyframes growUp {{ to {{ transform: scaleY(1); }} }}
  @keyframes wipeIn {{ to {{ transform: scaleX(1); }} }}
  @keyframes pulseGlow {{
    0% {{ box-shadow: 0 0 0 0 rgba(144,133,233,.55); }}
    70% {{ box-shadow: 0 0 0 7px rgba(144,133,233,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(144,133,233,0); }}
  }}

  :root {{
    --void: #09090b; --panel: #15151b; --panel-2: #1c1c24; --page: var(--void);
    --surface-1: var(--panel);
    --edge: #2a2a34; --border: var(--edge);
    --ink: #f3f3ef; --text-primary: var(--ink);
    --ink-dim: #96969f; --text-secondary: var(--ink-dim);
    --ink-faint: #5f5f69; --text-muted: var(--ink-faint);
    --grid: #212129; --baseline: #35353f;
    --red: #e2001c; --red-dim: rgba(226,0,28,.14); --accent: var(--red);
    --green: #17c974; --good: var(--green); --good-bg: rgba(23,201,116,.16);
    --amber: #ffb020; --amber-bg: rgba(255,176,32,.16);
    --purple: #9085e9; --purple-bg: rgba(144,133,233,.18);
    --cut: 12px;
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--void); }}
  body {{
    margin: 0; padding: 32px 16px 64px; background: var(--void); overflow-x: hidden;
    font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--ink);
  }}
  .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  h1, h2, h3, .session-badge, .rank, .chip {{
    font-family: 'Titillium Web', 'Segoe UI', sans-serif;
  }}
  .wrap {{ max-width: 1020px; margin: 0 auto; }}

  .hero {{
    position: relative; overflow: hidden;
    background: var(--panel) center/cover no-repeat; border: 1px solid var(--border);
    padding: 40px 28px 28px; margin-bottom: 22px;
    clip-path: polygon(var(--cut) 0, 100% 0, 100% 100%, 0 100%, 0 var(--cut));
  }}
  .hero--graphic {{ background-image: linear-gradient(135deg, var(--panel) 0%, var(--panel-2) 55%, var(--panel) 100%); }}
  .hero-sweep {{
    position: absolute; inset: 0 0 0 auto; width: 320px; pointer-events: none;
    background: linear-gradient(112deg,
      transparent 0 42%, rgba(226,0,28,.85) 42% 46%, transparent 46% 58%,
      rgba(226,0,28,.3) 58% 62%, transparent 62% 100%);
  }}
  .hero-top {{ position: relative; display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
  .session-badge {{
    font-weight: 900; font-size: 11.5px; letter-spacing: .07em; color: #fff;
    background: var(--badge-color, var(--red)); padding: 5px 12px 5px 9px; line-height: 1;
    clip-path: polygon(6px 0, 100% 0, 100% 100%, 0 100%, 0 6px);
  }}
  .hero-meta {{ color: var(--ink-dim); font-size: 12.5px; }}
  .hero-title {{
    position: relative; font-size: clamp(26px, 3.6vw, 38px); margin: 0 0 4px; font-weight: 900;
    letter-spacing: .01em; text-transform: uppercase; text-shadow: 0 2px 14px rgba(0,0,0,.7);
  }}
  .hero-sub {{ position: relative; color: var(--ink-dim); font-size: 13.5px; margin: 0; text-shadow: 0 2px 8px rgba(0,0,0,.7); }}
  .badge {{ width: 20px; height: 20px; object-fit: contain; margin-right: 8px; flex-shrink: 0; }}

  .card {{
    background: var(--panel); border: 1px solid var(--border);
    padding: 20px 22px; margin-bottom: 20px;
    clip-path: polygon(var(--cut) 0, 100% 0, 100% 100%, 0 100%, 0 var(--cut));
  }}
  .card h2 {{
    display: inline-block; margin: 0 0 6px; font-weight: 800; font-size: 12.5px;
    letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
    background: var(--panel-2); border-left: 3px solid var(--red);
    padding: 5px 12px 5px 9px; clip-path: polygon(0 0, 100% 0, calc(100% - 9px) 100%, 0 100%);
  }}
  .card .hint {{ display: block; font-size: 11.5px; color: var(--text-muted); margin: 0 0 14px; }}
  .podium-row {{ display: flex; gap: 12px; align-items: flex-end; margin-bottom: 18px; }}
  .podium-col {{ flex: 1; display: flex; flex-direction: column; align-items: center; min-width: 0; }}
  .podium-col .car-thumb {{ width: 100%; max-width: 110px; height: 62px; margin-bottom: 8px; border-top: 2px solid var(--driver-color, var(--edge)); }}
  .podium-box {{
    width: 100%; padding: 10px 8px; color: var(--page); text-align: center;
    box-sizing: border-box; min-height: 0; transform-origin: bottom;
    clip-path: polygon(10px 0, 100% 0, 100% 100%, 0 100%, 0 10px);
  }}
  .podium-box .rank {{ font-weight: 900; font-size: 17px; }}
  .podium-box .name {{ font-weight: 700; font-size: 13px; margin-top: 4px; font-family: 'Inter', sans-serif; }}
  .podium-box .lap {{ font-size: 11px; opacity: 0.85; margin-top: 2px; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: var(--text-secondary); font-weight: 700; padding: 6px 8px; border-bottom: 1px solid var(--baseline);
        font-size: 11px; letter-spacing: .03em; text-transform: uppercase; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }}
  td.pos {{ font-weight: 800; }}
  tbody tr {{ box-shadow: inset 2px 0 0 transparent; transition: background .15s, box-shadow .15s; }}
  tbody tr:hover {{ background: var(--panel-2); box-shadow: inset 2px 0 0 var(--red); }}
  .delta {{ font-weight: 700; font-size: 12px; white-space: nowrap; }}
  .delta-up {{ color: var(--green); }}
  .delta-down {{ color: var(--red); }}
  .delta-flat {{ color: var(--ink-faint); }}
  .pen-tag {{
    display: inline-block; font-size: 10px; font-weight: 800; color: var(--red);
    border: 1px solid var(--red); padding: 1px 5px; margin-left: 4px; letter-spacing: .02em;
  }}
  span.good {{ color: var(--good); font-weight: 700; }}
  span.bad {{ color: var(--red); font-weight: 700; }}
  .pen-item {{ font-size: 12px; color: var(--text-secondary); }}
  .pen-item + .pen-item {{ margin-top: 3px; }}
  .chip {{ display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 20px;
           font-size: 10.5px; font-weight: 900; color: var(--page); margin-right: 8px;
           clip-path: polygon(4px 0, 100% 0, 100% 100%, 0 100%, 0 4px); }}
  .filterbar {{ display: flex; gap: 6px; margin-bottom: 10px; }}
  .filterbar button {{
    background: transparent; border: 1px solid var(--baseline); color: var(--text-secondary);
    padding: 5px 12px 5px 10px; font-size: 11px; cursor: pointer; font-weight: 700;
    font-family: 'Titillium Web', sans-serif; letter-spacing: .04em; text-transform: uppercase;
    clip-path: polygon(5px 0, 100% 0, 100% 100%, 0 100%, 0 5px);
    transition: border-color .12s, color .12s, background .12s;
  }}
  .filterbar button:hover {{ border-color: var(--red); color: var(--ink); background: var(--red-dim); }}
  .legend {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }}
  .legend .key {{
    display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary);
    cursor: pointer; padding: 4px 9px 4px 5px; border-radius: 20px; border: 1px solid transparent;
    user-select: none; white-space: nowrap; flex-shrink: 0; background: none; font: inherit;
    appearance: none; -webkit-appearance: none; font-family: 'Inter', sans-serif;
    transition: border-color .12s, transform .12s;
  }}
  .legend .key:hover {{ border-color: var(--baseline); transform: translateY(-1px); }}
  .legend .key.off {{ opacity: 0.35; }}
  .legend .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
  .chart-box {{ position: relative; }}
  svg {{ width: 100%; height: auto; display: block; }}
  .tooltip {{
    position: absolute; pointer-events: none; background: #000000; color: white;
    padding: 8px 10px; font-size: 12px; line-height: 1.5;
    transform: translate(-50%, -110%); opacity: 0; transition: opacity 0.08s; white-space: nowrap;
    z-index: 5; border: 1px solid var(--border); max-height: 260px; overflow-y: auto;
    clip-path: polygon(6px 0, 100% 0, 100% 100%, 0 100%, 0 6px);
  }}
  .tooltip .row {{ display: flex; gap: 10px; justify-content: space-between; }}
  .tooltip .val {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .tooltip .lbl {{ color: #d8d8d4; display: flex; align-items: center; gap: 5px; }}
  details summary {{ cursor: pointer; font-size: 12.5px; color: var(--text-secondary); margin-top: 10px; }}
  details summary::-webkit-details-marker {{ display: none; }}
  .crosshair {{ stroke: var(--baseline); stroke-width: 1; }}
  .car-thumb {{ width: 44px; height: 25px; object-fit: cover; vertical-align: middle; margin-right: 8px; flex-shrink: 0; }}
  .driver-cell {{ display: flex; align-items: center; }}
  .circuit-row {{ display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }}
  .circuit-map {{
    width: 280px; height: 170px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }}
  .circuit-map img {{ max-width: 100%; max-height: 100%; width: auto; height: auto; }}
  .circuit-stats {{ display: flex; flex-wrap: wrap; gap: 20px 36px; align-content: center; }}
  .circuit-stats .stat {{ min-width: 80px; }}
  .circuit-stats .stat .v {{ font-size: 16px; font-weight: 800; font-family: 'Titillium Web', sans-serif; }}
  .circuit-stats .stat .l {{ font-size: 10.5px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.4px; }}
  .sector-grid {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .sector-col {{ flex: 1; min-width: 150px; }}
  .sector-col h3 {{
    font-size: 11px; font-weight: 800; letter-spacing: .05em; text-transform: uppercase;
    color: var(--text-muted); margin: 0 0 8px;
  }}
  .sector-rank {{ list-style: none; margin: 0; padding: 0; }}
  .sector-rank li {{
    display: flex; align-items: center; gap: 8px; padding: 5px 0;
    border-bottom: 1px solid var(--grid); font-size: 13px;
  }}
  .sector-rank li:last-child {{ border-bottom: none; }}
  .sector-driver {{ flex: 1; font-weight: 700; }}
  .sector-time {{ font-variant-numeric: tabular-nums; color: var(--text-secondary); }}
  .sector-rank li.fastest .sector-time {{ color: var(--purple); font-weight: 800; }}
  .timing-table td.purple {{ background: var(--purple-bg); color: var(--purple); font-weight: 700; }}
  .timing-table td.good {{ background: var(--good-bg); color: var(--good); font-weight: 700; }}
  .timing-table td.lapnum.cut-warn {{ box-shadow: inset 3px 0 0 var(--amber); }}
  .timing-table td.lapnum.cut-pen {{ box-shadow: inset 3px 0 0 var(--red); }}
  .timing-table th, .timing-table td {{ text-align: right; }}
  .timing-table th:first-child, .timing-table td:first-child {{ text-align: left; }}
  .driver-group summary {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-primary); font-weight: 700; list-style: none; }}
  .driver-group summary::-webkit-details-marker {{ display: none; }}
  .driver-group summary::before {{
    content: ''; display: inline-block; width: 0; height: 0; margin-right: 2px;
    border-left: 5px solid var(--ink-dim); border-top: 4px solid transparent; border-bottom: 4px solid transparent;
    transition: transform .2s;
  }}
  .driver-group[open] summary::before {{ transform: rotate(90deg); }}
  .driver-group {{ margin-bottom: 10px; border-bottom: 1px solid var(--grid); padding-bottom: 8px; }}
  .legend-note {{ display: flex; gap: 16px; font-size: 11.5px; color: var(--text-muted); margin: 8px 0 14px; }}
  .legend-note .sw {{ display: inline-block; width: 10px; height: 10px; margin-right: 5px; vertical-align: -1px; }}
  :focus-visible {{ outline: 2px solid var(--red); outline-offset: 2px; }}
  @media (max-width: 560px) {{
    :root {{ --cut: 8px; }}
    .hero {{ padding: 30px 18px 20px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero{hero_class}" style="{hero_style}">
    <div class="hero-sweep"></div>
    <div class="hero-top">
      <span class="session-badge" style="--badge-color:{session_badge_color}">{session_type}</span>
      <span class="hero-meta">{driver_count_text}</span>
    </div>
    <h1 class="hero-title">{title}</h1>
    <p class="hero-sub">{subtitle}</p>
  </div>

  {circuit_html}

  <div class="card">
    <h2>Podium</h2>
    <div class="podium-row">{podium_html}</div>
    <div class="table-scroll">
    <table>
      <thead><tr><th>Pos</th><th title="Places gained or lost since lap 1">+/-</th><th>Driver</th><th>Car</th><th>Gap</th><th>Best lap</th><th title="Average lap time of laps set with zero track-limit cuts">Avg clean lap</th><th>Laps</th></tr></thead>
      <tbody>{classification_rows}</tbody>
    </table>
    </div>
  </div>

  {chart_cards}

  <div class="card">
    <h2>Tyre strategy</h2>
    {tyre_html}
  </div>

  {sector_html}

  <div class="card">
    <h2>Lap times</h2>
    <p class="hint">Per-driver sector and lap times. Click a driver to expand.</p>
    <div class="legend-note">
      <span><span class="sw" style="background:var(--purple)"></span>Fastest of the race</span>
      <span><span class="sw" style="background:var(--good)"></span>Driver's personal best</span>
    </div>
    {timing_html}
  </div>

  {incidents_html}
</div>

<script>
let __chartRevealOrder = 0;
const __reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function renderLineChart(containerId, data, opts) {{
  opts = opts || {{}};
  const container = document.getElementById(containerId);
  const legendEl = document.getElementById(containerId + "-legend");
  const filterEl = document.getElementById(containerId + "-filters");
  const W = 940, H = 340, padL = 46, padR = 46, padT = 16, padB = 36;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const maxLap = data.maxLap;
  const series = data.series;
  const invert = !!opts.invertY;
  const visible = {{}};
  const chartDelayBase = __chartRevealOrder++ * 150;
  let firstDraw = true;
  series.forEach(s => visible[s.code] = true);

  function percentile(sortedArr, p) {{
    if (!sortedArr.length) return 0;
    const idx = (sortedArr.length - 1) * p;
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    return lo === hi ? sortedArr[lo] : sortedArr[lo] + (sortedArr[hi] - sortedArr[lo]) * (idx - lo);
  }}

  function computeRange() {{
    const vals = [];
    series.forEach(s => s.values.forEach(v => {{ if (v !== null) vals.push(v); }}));
    if (!vals.length) return [0, 1];
    if (invert) return [Math.min(...vals), Math.max(...vals)];
    vals.sort((a, b) => a - b);
    let lo = percentile(vals, 0.03), hi = percentile(vals, 0.97);
    const pad = (hi - lo) * 0.25 || hi * 0.1 || 1;
    lo -= pad; hi += pad;
    if (opts.minZero) lo = Math.max(0, lo);
    return [lo, hi];
  }}

  const [vMin, vMax] = computeRange();
  const x = i => padL + (innerW * i) / Math.max(maxLap - 1, 1);
  const y = v => {{
    const t = (v - vMin) / (vMax - vMin);
    return invert ? padT + t * innerH : padT + (1 - t) * innerH;
  }};

  function path(values) {{
    let d = "", started = false;
    values.forEach((v, i) => {{
      if (v === null) {{ started = false; return; }}
      d += (started ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1) + " ";
      started = true;
    }});
    return d;
  }}

  function draw() {{
    let svg = `<svg viewBox="0 0 ${{W}} ${{H}}">`;
    const ticks = 5;
    for (let t = 0; t <= ticks; t++) {{
      const v = vMin + (t / ticks) * (vMax - vMin);
      const yy = y(v);
      svg += `<line x1="${{padL}}" x2="${{W - padR}}" y1="${{yy}}" y2="${{yy}}" stroke="${{GRID}}" stroke-width="1"/>`;
      svg += `<text x="${{padL - 8}}" y="${{yy + 3}}" font-size="10" fill="${{MUTED}}" text-anchor="end">${{opts.yFmt ? opts.yFmt(v) : v.toFixed(1)}}</text>`;
    }}
    svg += `<line x1="${{padL}}" x2="${{padL}}" y1="${{padT}}" y2="${{H - padB}}" stroke="${{BASELINE}}" stroke-width="1"/>`;
    svg += `<line x1="${{padL}}" x2="${{W - padR}}" y1="${{H - padB}}" y2="${{H - padB}}" stroke="${{BASELINE}}" stroke-width="1"/>`;
    const xTickStep = Math.max(1, Math.round(maxLap / 10));
    for (let lap = 1; lap <= maxLap; lap += xTickStep) {{
      svg += `<text x="${{x(lap - 1)}}" y="${{H - padB + 16}}" font-size="10" fill="${{MUTED}}" text-anchor="middle">${{lap}}</text>`;
    }}

    const clipId = containerId + "-clip";
    svg += `<clipPath id="${{clipId}}"><rect x="${{padL}}" y="${{padT}}" width="${{innerW}}" height="${{innerH}}"/></clipPath>`;
    svg += `<g clip-path="url(#${{clipId}})">`;
    let lineCount = 0;
    series.forEach(s => {{
      if (!visible[s.code]) return;
      const dash = s.dash ? `stroke-dasharray="${{s.dash}}"` : "";
      svg += `<path data-line="1" data-idx="${{lineCount++}}" d="${{path(s.values)}}" fill="none" stroke="${{s.color}}" stroke-width="2" ${{dash}}/>`;
    }});
    svg += `</g>`;
    // Collect end points first, then declutter in pixel space so close
    // finishers' code labels don't print on top of each other.
    let decorSvg = "";
    const endPoints = [];
    series.forEach(s => {{
      if (!visible[s.code]) return;
      for (let i = s.values.length - 1; i >= 0; i--) {{
        if (s.values[i] !== null) {{
          const px = x(i), py = y(s.values[i]);
          decorSvg += `<circle cx="${{px}}" cy="${{py}}" r="3.5" fill="${{s.color}}" stroke="${{SURFACE}}" stroke-width="1.5"/>`;
          endPoints.push({{px, py, code: s.code, color: s.color}});
          break;
        }}
      }}
    }});
    endPoints.sort((a, b) => a.py - b.py);
    const minGap = 12;
    for (let i = 1; i < endPoints.length; i++) {{
      if (endPoints[i].py - endPoints[i - 1].py < minGap) {{
        endPoints[i].py = endPoints[i - 1].py + minGap;
      }}
    }}
    endPoints.forEach(p => {{
      decorSvg += `<text x="${{p.px + 7}}" y="${{p.py + 3}}" font-size="9.5" fill="${{p.color}}" font-weight="700">${{p.code}}</text>`;
    }});
    svg += `<g class="chart-decor">${{decorSvg}}</g>`;
    svg += `<line id="${{containerId}}-crosshair" class="crosshair" x1="0" x2="0" y1="${{padT}}" y2="${{H - padB}}" opacity="0"/>`;
    svg += `<rect id="${{containerId}}-hit" x="${{padL}}" y="${{padT}}" width="${{innerW}}" height="${{innerH}}" fill="transparent"/>`;
    svg += `</svg>`;
    container.innerHTML = svg + `<div class="tooltip" id="${{containerId}}-tooltip"></div>`;
    attachHover();
    if (firstDraw) {{
      firstDraw = false;
      if (!__reduceMotion) animateReveal();
    }}
  }}

  // Lines draw themselves in once, like a race trace building lap by lap --
  // only on the chart's first render, never on legend/filter re-draws.
  function animateReveal() {{
    const svgEl = container.querySelector("svg");
    const lines = svgEl.querySelectorAll("path[data-line]");
    lines.forEach(p => {{
      const len = p.getTotalLength();
      p.style.strokeDasharray = len;
      p.style.strokeDashoffset = len;
      const delay = chartDelayBase + Number(p.dataset.idx) * 80;
      requestAnimationFrame(() => requestAnimationFrame(() => {{
        p.style.transition = `stroke-dashoffset .85s cubic-bezier(.3,.7,.2,1) ${{delay}}ms`;
        p.style.strokeDashoffset = 0;
      }}));
    }});
    const decor = svgEl.querySelector(".chart-decor");
    if (decor) {{
      decor.style.opacity = "0";
      const decorDelay = chartDelayBase + lines.length * 80 + 200;
      requestAnimationFrame(() => requestAnimationFrame(() => {{
        decor.style.transition = `opacity .4s ease ${{decorDelay}}ms`;
        decor.style.opacity = "1";
      }}));
    }}
  }}

  function attachHover() {{
    const hit = document.getElementById(containerId + "-hit");
    const crosshair = document.getElementById(containerId + "-crosshair");
    const tooltip = document.getElementById(containerId + "-tooltip");
    const svgEl = container.querySelector("svg");
    hit.addEventListener("pointermove", (e) => {{
      const rect = svgEl.getBoundingClientRect();
      const scaleX = W / rect.width;
      const mx = (e.clientX - rect.left) * scaleX;
      let lap = Math.round(((mx - padL) / innerW) * (maxLap - 1));
      lap = Math.max(0, Math.min(maxLap - 1, lap));
      crosshair.setAttribute("x1", x(lap)); crosshair.setAttribute("x2", x(lap));
      crosshair.setAttribute("opacity", "1");
      let rows = "";
      series.filter(s => visible[s.code]).sort((a, b) => {{
        const av = a.values[lap], bv = b.values[lap];
        if (av === null) return 1; if (bv === null) return -1;
        return invert ? av - bv : av - bv;
      }}).forEach(s => {{
        const v = s.values[lap];
        if (v === null) return;
        rows += `<div class="row"><span class="lbl"><span class="dot" style="width:8px;height:8px;background:${{s.color}}"></span>${{s.code}}</span><span class="val">${{opts.yFmt ? opts.yFmt(v) : v.toFixed(2)}}</span></div>`;
      }});
      tooltip.innerHTML = `<div style="font-weight:700;margin-bottom:4px">Lap ${{lap + 1}}</div>` + rows;
      tooltip.style.left = (x(lap) / W * rect.width) + "px";
      tooltip.style.top = (padT / H * rect.height) + "px";
      tooltip.style.opacity = "1";
    }});
    hit.addEventListener("pointerleave", () => {{
      crosshair.setAttribute("opacity", "0");
      tooltip.style.opacity = "0";
    }});
  }}

  function renderLegend() {{
    legendEl.innerHTML = "";
    series.forEach(s => {{
      const el = document.createElement("button");
      el.type = "button";
      el.className = "key" + (visible[s.code] ? "" : " off");
      el.innerHTML = `<span class="dot" style="background:${{s.color}}"></span>P${{s.pos}} ${{s.code}} — ${{s.label}}`;
      el.addEventListener("click", () => {{
        visible[s.code] = !visible[s.code];
        el.classList.toggle("off", !visible[s.code]);
        draw();
      }});
      legendEl.appendChild(el);
    }});
  }}

  function setAll(on) {{ series.forEach(s => visible[s.code] = on); }}

  if (filterEl) {{
    const presets = [
      ["All", () => setAll(true)],
      ["Top 3", () => {{ setAll(false); series.filter(s => s.pos <= 3).forEach(s => visible[s.code] = true); }}],
      ["Top 5", () => {{ setAll(false); series.filter(s => s.pos <= 5).forEach(s => visible[s.code] = true); }}],
      ["None", () => setAll(false)],
    ];
    presets.forEach(([label, fn]) => {{
      const b = document.createElement("button");
      b.textContent = label;
      b.addEventListener("click", () => {{ fn(); renderLegend(); draw(); }});
      filterEl.appendChild(b);
    }});
  }}

  const GRID = "#212129", MUTED = "#5f5f69", BASELINE = "#35353f", SURFACE = "#15151b";
  renderLegend();
  draw();
}}
{chart_inits}
</script>
</body>
</html>
"""


SESSION_BADGE_COLORS = {
    "RACE": "var(--red)",
    "QUALIFY": "var(--purple)",
    "QUALIFYING": "var(--purple)",
    "PRACTICE": "#5f5f69",
}


def position_deltas(laps_df):
    """Places gained (+) or lost (-) between a driver's first and last
    recorded lap -- the broadcast-standard 'form' indicator next to a
    finishing position."""
    deltas = {}
    if laps_df.empty or "position" not in laps_df.columns:
        return deltas
    for key, g in laps_df.groupby("key"):
        g = g.sort_values("lap_number")
        deltas[key] = int(g.iloc[0]["position"]) - int(g.iloc[-1]["position"])
    return deltas


def render_html(data, classification, laps_df, title, out_path,
                  car_thumbs=None, badges=None, outline_rel=None, preview_rel=None,
                  track_meta=None, sector_bests=None, incidents=None, pit_stops=None):
    styles = driver_styles(classification)
    car_thumbs = car_thumbs or {}
    badges = badges or {}
    incidents = incidents or {}
    pit_stops = pit_stops or {}
    session_type = (data.get("Type") or "SESSION").upper()
    session_badge_color = SESSION_BADGE_COLORS.get(session_type, "var(--red)")
    driver_count_text = f"{len(classification)} driver" + ("" if len(classification) == 1 else "s")
    location_bits = [x for x in ((track_meta or {}).get("city"), (track_meta or {}).get("country")) if x]
    subtitle = ", ".join(location_bits) if location_bits else driver_count_text
    deltas = position_deltas(laps_df)

    podium_html = ""
    order = [1, 0, 2]
    flex = {0: 1.2, 1: 1.0, 2: 0.85}
    heightpx = {0: 150, 1: 110, 2: 85}
    for reveal_idx, idx in enumerate(order):
        if idx >= len(classification):
            continue
        row = classification.iloc[idx]
        key = (row["guid"], row["car_id"])
        color = styles[key]["color"]
        thumb = car_thumbs.get(key)
        img_tag = f'<img class="car-thumb" style="--driver-color:{color}" src="{thumb}" alt="">' if thumb else ""
        podium_html += (
            f'<div class="podium-col" style="flex:{flex[idx]}">'
            f'{img_tag}'
            f'<div class="podium-box" style="background:{color};height:{heightpx[idx]}px;'
            f'display:flex;flex-direction:column;justify-content:flex-end;animation-delay:{reveal_idx * 0.12:.2f}s">'
            f'<div class="rank">P{idx + 1}</div>'
            f'<div class="name">{esc(short_name(row["driver"], 16))}</div>'
            f'<div class="lap">{esc(fmt_ms(row["best_lap_ms"]))}</div>'
            f'</div>'
            f'</div>'
        )

    classification_rows = ""
    for _, row in classification.iterrows():
        key = (row["guid"], row["car_id"])
        s = styles[key]
        thumb = car_thumbs.get(key)
        img_tag = f'<img class="car-thumb" src="{thumb}" alt="">' if thumb else ""
        badge = badges.get(row["car"])
        badge_tag = f'<img class="badge" src="{badge}" alt="">' if badge else ""
        d = deltas.get(key, 0)
        if d > 0:
            delta_html = f'<span class="delta delta-up">▲{d}</span>'
        elif d < 0:
            delta_html = f'<span class="delta delta-down">▼{abs(d)}</span>'
        else:
            delta_html = '<span class="delta delta-flat">—</span>'
        pen_s = incidents.get(row["guid"], {}).get("time_penalty_s", 0)
        pen_tag = (
            f'<span class="pen-tag" title="{pen_s}s time penalty included (penalty not served on track)">+{pen_s}s</span>'
            if pen_s else ""
        )
        classification_rows += (
            f'<tr><td class="pos"><span class="chip" style="background:{s["color"]}">{row["pos"]}</span></td>'
            f'<td>{delta_html}</td>'
            f'<td><div class="driver-cell">{img_tag}<span>{esc(row["driver"])} '
            f'<span style="color:var(--text-muted);font-size:11px">({esc(s["code"])})</span></span></div></td>'
            f'<td><div class="driver-cell">{badge_tag}<span>{esc(row["car"])}</span></div></td>'
            f'<td>{esc(row["gap"])} {pen_tag}</td>'
            f'<td>{esc(fmt_ms(row["best_lap_ms"]))}</td>'
            f'<td>{esc(fmt_ms(row["avg_clean_ms"])) if row["avg_clean_ms"] else "—"}</td>'
            f'<td>{row["laps"]}</td></tr>'
        )

    charts = [
        ("pace", "Race pace", "Lap time (s)", "LapTime_s", False, "s", True),
        ("gaps", "Gap to leader", "Gap (s)", "gap_s", False, "s", True),
        ("positions", "Position by lap", "Position", "position", True, "pos", False),
    ]
    laps_df = laps_df.copy()
    if not laps_df.empty:
        laps_df["LapTime_s"] = laps_df["LapTime"] / 1000.0

    chart_cards = ""
    chart_inits = ""
    for cid, ctitle, ylabel, col, invert, fmt_kind, min_zero in charts:
        if laps_df.empty or col not in laps_df.columns:
            continue
        payload = chart_series_json(laps_df, classification, col)

        table_rows = ""
        for lap in range(payload["maxLap"]):
            cells = "".join(
                f"<td>{s['values'][lap] if s['values'][lap] is not None else '—'}</td>"
                for s in payload["series"]
            )
            table_rows += f"<tr><td>{lap + 1}</td>{cells}</tr>"
        table_header = "".join(f"<th>{esc(s['code'])}</th>" for s in payload["series"])

        chart_cards += f"""
  <div class="card">
    <h2>{ctitle}</h2>
    <p class="hint">Click a driver to isolate them, or use the quick filters. Hover the chart for exact gaps.</p>
    <div class="filterbar" id="{cid}-filters"></div>
    <div class="legend" id="{cid}-legend"></div>
    <div class="chart-box" id="{cid}"></div>
    <details><summary>Show data table</summary>
      <div class="table-scroll">
      <table><thead><tr><th>Lap</th>{table_header}</tr></thead><tbody>{table_rows}</tbody></table>
      </div>
    </details>
  </div>"""

        y_fmt = {
            "s": "function(v){return v.toFixed(1)+\"s\";}",
            "pos": "function(v){return \"P\"+Math.round(v);}",
        }[fmt_kind]
        chart_inits += (
            f"renderLineChart('{cid}', {json.dumps(payload)}, "
            f"{{invertY: {str(invert).lower()}, minZero: {str(min_zero).lower()}, yFmt: {y_fmt}}});\n"
        )

    tyre_html = "<p style='color:var(--text-muted);font-size:13px'>No tyre data available.</p>"
    if not laps_df.empty:
        order_df = classification.sort_values("pos")
        rows_html = ""
        seen = set()
        shown = 0
        for _, row in order_df.iterrows():
            key = (row["guid"], row["car_id"])
            g = laps_df[laps_df["key"] == key].sort_values("lap_number")
            if g.empty:
                continue
            s = styles.get(key, {"code": "???", "color": MUTED})
            stops_by_in_lap = {st["in_lap"]: st for st in pit_stops.get(row["guid"], [])}
            tyre_by_lap = {int(l): t for l, t in zip(g["lap_number"], g["Tyre"])}
            cells = ""
            for _, lap in g.iterrows():
                lap_num = int(lap["lap_number"])
                tyre = lap.get("Tyre") or "?"
                color = TYRE_COLORS.get(tyre, MUTED)
                seen.add(tyre)
                extra_style, extra_title = "", ""
                stop = stops_by_in_lap.get(lap_num)
                if stop:
                    tyre_after = tyre_by_lap.get(stop["out_lap"]) if stop["out_lap"] else None
                    changed = stop["out_lap"] is not None and tyre_after is not None and tyre_after != tyre
                    if changed:
                        extra_style = "box-shadow:inset 0 0 0 2px #fff;filter:brightness(1.2);"
                        extra_title = f" — pit stop, tyres changed to {esc(TYRE_NAMES.get(tyre_after, tyre_after))}"
                    else:
                        extra_style = "box-shadow:inset 0 -4px 0 0 rgba(255,255,255,.6);"
                        extra_title = " — pit stop, same tyres"
                cells += (f'<div style="flex:1;background:{color};border-radius:2px;min-width:2px;{extra_style}" '
                           f'title="{esc(s["code"])} lap {lap_num}: {esc(TYRE_NAMES.get(tyre, tyre))}{extra_title}"></div>')
            rows_html += (
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                f'<div style="width:50px;font-size:12px;color:{s["color"]};font-weight:700;flex-shrink:0">{esc(s["code"])}</div>'
                f'<div class="tyre-bars" style="display:flex;gap:2px;flex:1;height:18px;transform-origin:left;animation-delay:{shown * 0.08:.2f}s">{cells}</div>'
                f'</div>'
            )
            shown += 1
        legend_bits = "".join(
            f'<span class="key" style="cursor:default">{tyre_icon_svg(TYRE_COLORS.get(t, MUTED))}{esc(TYRE_NAMES.get(t, t))}</span>'
            for t in sorted(seen)
        )
        pit_legend = ""
        if any(pit_stops.values()):
            pit_legend = (
                '<div class="legend-note">'
                '<span><span class="sw" style="background:rgba(255,255,255,.6)"></span>Pit stop, same tyres</span>'
                '<span><span class="sw" style="background:#fff;box-shadow:0 0 0 2px #fff"></span>Pit stop, tyres changed</span>'
                '</div>'
            )
        tyre_html = f'<div class="legend">{legend_bits}</div>' + pit_legend + rows_html

    circuit_html = ""
    if outline_rel or track_meta:
        stats_html = ""
        if track_meta:
            for label, k in (("Length", "length"), ("Corners", "corner"), ("Pit boxes", "pitboxes"),
                               ("Width", "width"), ("Direction", "run")):
                v = track_meta.get(k)
                if v:
                    stats_html += f'<div class="stat"><div class="v">{esc(str(v).title() if k == "run" else v)}</div><div class="l">{esc(label)}</div></div>'
        img_html = f'<div class="circuit-map"><img src="{outline_rel}" alt="Circuit outline"></div>' if outline_rel else ""
        name = (track_meta or {}).get("name", "")
        circuit_html = f"""
  <div class="card">
    <h2>Circuit</h2>
    <p class="hint">{esc(name)}</p>
    <div class="circuit-row">
      {img_html}
      <div class="circuit-stats">{stats_html}</div>
    </div>
  </div>"""

    timing_html = _build_timing_html(laps_df, classification, styles, sector_bests, incidents)
    incidents_html = _build_incidents_html(classification, incidents, styles)
    sector_html = _build_sector_html(classification, styles, sector_bests)
    if preview_rel:
        hero_class = ""
        hero_style = f"background-image:linear-gradient(180deg, rgba(13,13,13,0.35), rgba(13,13,13,0.85)), url('{preview_rel}')"
    else:
        # No preview photo sharp enough for full-banner width (see
        # prepare_assets) -- fall back to a plain gradient panel rather than
        # stretching a blurry one.
        hero_class = " hero--graphic"
        hero_style = ""

    html_out = HTML_TEMPLATE.format(
        title=esc(title),
        subtitle=esc(subtitle),
        session_type=esc(session_type),
        session_badge_color=session_badge_color,
        driver_count_text=esc(driver_count_text),
        hero_class=hero_class,
        hero_style=hero_style,
        podium_html=podium_html,
        classification_rows=classification_rows,
        chart_cards=chart_cards,
        tyre_html=tyre_html,
        circuit_html=circuit_html,
        timing_html=timing_html,
        incidents_html=incidents_html,
        sector_html=sector_html,
        chart_inits=chart_inits,
    )
    Path(out_path).write_text(html_out, encoding="utf-8")


def _cell_class(value, overall_best, personal_best):
    if value is None or value <= 0:
        return ""
    if overall_best is not None and abs(value - overall_best) < 0.5:
        return "purple"
    if personal_best is not None and abs(value - personal_best) < 0.5:
        return "good"
    return ""


def _build_sector_html(classification, styles, sector_bests):
    """No speed telemetry exists in this setup, so sector splits are the
    closest honest read on who's quicker through which part of the lap --
    ranks each driver's personal-best time per sector."""
    personal_sectors = sector_bests.get("personal_sectors") or {}
    n_sectors = len(sector_bests.get("overall_sectors") or [])
    if not n_sectors or not personal_sectors:
        return ""

    cols_html = ""
    for i in range(n_sectors):
        ranked = []
        for _, row in classification.iterrows():
            key = (row["guid"], row["car_id"])
            vals = personal_sectors.get(key)
            if vals and i < len(vals) and vals[i]:
                ranked.append((vals[i], row, key))
        if not ranked:
            continue
        ranked.sort(key=lambda t: t[0])
        items = ""
        for pos, (v, row, key) in enumerate(ranked, start=1):
            s = styles[key]
            cls = " class=\"fastest\"" if pos == 1 else ""
            items += (
                f'<li{cls}><span class="chip" style="background:{s["color"]}">{pos}</span>'
                f'<span class="sector-driver">{esc(s["code"])}</span>'
                f'<span class="sector-time">{fmt_ms(v)}</span></li>'
            )
        cols_html += f'<div class="sector-col"><h3>Sector {i + 1}</h3><ol class="sector-rank">{items}</ol></div>'

    if not cols_html:
        return ""
    return f"""
  <div class="card">
    <h2>Best sectors</h2>
    <p class="hint">Each driver's personal-best time per sector, ranked fastest to slowest.</p>
    <div class="sector-grid">{cols_html}</div>
  </div>"""


def _build_timing_html(laps_df, classification, styles, sector_bests, incidents=None):
    if laps_df.empty or not sector_bests or not sector_bests.get("overall_sectors"):
        return "<p style='color:var(--text-muted);font-size:13px'>No lap data available.</p>"

    incidents = incidents or {}
    overall_sectors = sector_bests["overall_sectors"]
    overall_lap = sector_bests["overall_lap"]
    personal_sectors = sector_bests["personal_sectors"]
    personal_lap = sector_bests["personal_lap"]
    n_sectors = len(overall_sectors)

    out = ""
    for _, row in classification.sort_values("pos").iterrows():
        key = (row["guid"], row["car_id"])
        g = laps_df[laps_df["key"] == key].sort_values("lap_number")
        if g.empty:
            continue
        s = styles[key]
        pb_sectors = personal_sectors.get(key, [None] * n_sectors)
        pb_lap = personal_lap.get(key)
        inc = incidents.get(row["guid"], {})
        warning_laps = set(inc.get("warning_laps", []))
        penalty_laps = {int(p["lap"]) for p in inc.get("penalties", [])}
        body_rows = ""
        for _, lap in g.iterrows():
            sectors = lap.get("Sectors") or []
            cells = ""
            for i in range(n_sectors):
                v = sectors[i] if i < len(sectors) else None
                cls = _cell_class(v, overall_sectors[i] if i < len(overall_sectors) else None,
                                    pb_sectors[i] if i < len(pb_sectors) else None)
                cells += f'<td class="{cls}">{fmt_ms(v) if v else "—"}</td>'
            lap_cls = _cell_class(lap.get("LapTime"), overall_lap, pb_lap)
            cells += f'<td class="{lap_cls}">{fmt_ms(lap.get("LapTime"))}</td>'
            lap_num = int(lap["lap_number"])
            native_dirty = (lap.get("Cuts") or 0) > 0
            if lap_num in penalty_laps:
                flag_cls, flag_title = " cut-pen", "Penalty issued on this lap"
            elif lap_num in warning_laps or native_dirty:
                flag_cls, flag_title = " cut-warn", "Cutting warning on this lap"
            else:
                flag_cls, flag_title = "", ""
            title_attr = f' title="{flag_title}"' if flag_title else ""
            body_rows += f'<tr><td class="lapnum{flag_cls}"{title_attr}>{lap_num}</td>{cells}</tr>'

        sector_headers = "".join(f"<th>S{i + 1}</th>" for i in range(n_sectors))
        open_attr = " open" if row["pos"] <= 3 else ""
        out += f"""
    <details class="driver-group"{open_attr}>
      <summary><span class="chip" style="background:{s['color']}">P{int(row['pos'])}</span>{esc(s['code'])} — {esc(row['driver'])}</summary>
      <div class="table-scroll">
      <table class="timing-table">
        <thead><tr><th>Lap</th>{sector_headers}<th>Lap time</th></tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
      </div>
    </details>"""
    return out


_PENALTY_STATUS_CLASS = {"served": "good", "wrong attempt": "bad", "issued": "bad"}
_PENALTY_STATUS_LABEL = {"served": "Served", "wrong attempt": "Served incorrectly", "issued": "Not served"}


def _build_incidents_html(classification, incidents, styles):
    if not incidents:
        return ""

    rows_html = ""
    any_incident = False
    for _, row in classification.iterrows():
        inc = incidents.get(row["guid"])
        crashes = (inc or {}).get("crashes") or {}
        n_crashes = crashes.get("car", 0) + crashes.get("env", 0)
        if not inc or not (inc["warnings"] or inc["penalties"] or inc["time_penalty_s"] or n_crashes):
            continue
        any_incident = True
        key = (row["guid"], row["car_id"])
        s = styles[key]

        warn_html = str(inc["warnings"]) if inc["warnings"] else "—"

        if inc["penalties"]:
            items = ""
            for p in inc["penalties"]:
                cls = _PENALTY_STATUS_CLASS.get(p["status"], "bad")
                label = _PENALTY_STATUS_LABEL.get(p["status"], p["status"])
                items += (
                    f'<div class="pen-item">{esc(p["type"])} '
                    f'— {esc(p["cause"])}, lap {esc(p["lap"])} — <span class="{cls}">{esc(label)}</span></div>'
                )
            pen_html = items
        else:
            pen_html = "—"

        if n_crashes:
            bits = []
            if crashes.get("car"):
                bits.append(f'{crashes["car"]} car')
            if crashes.get("env"):
                bits.append(f'{crashes["env"]} wall/track')
            crash_html = (
                f'<span class="bad">{n_crashes}</span> '
                f'<span style="color:var(--text-muted);font-size:11.5px">({", ".join(bits)} '
                f'· max {crashes["max_speed"]:.0f} km/h)</span>'
            )
        else:
            crash_html = "—"

        time_pen_html = f'<span class="bad">+{inc["time_penalty_s"]}s</span>' if inc["time_penalty_s"] else "—"

        rows_html += (
            f'<tr><td><div class="driver-cell"><span class="chip" style="background:{s["color"]}">'
            f'{int(row["pos"])}</span><span>{esc(row["driver"])}</span></div></td>'
            f'<td>{warn_html}</td>'
            f'<td>{pen_html}</td>'
            f'<td>{crash_html}</td>'
            f'<td>{time_pen_html}</td></tr>'
        )

    if not any_incident:
        return """
  <div class="card">
    <h2>Incidents</h2>
    <p class="hint">Clean race — no cutting warnings, penalties or crashes logged.</p>
  </div>"""

    return f"""
  <div class="card">
    <h2>Incidents</h2>
    <p class="hint">Cutting warnings, penalties and crashes, from the server's own logs.</p>
    <div class="legend-note">
      <span><span class="sw" style="background:var(--amber)"></span>Lap with a cutting warning</span>
      <span><span class="sw" style="background:var(--red)"></span>Lap a penalty was issued on</span>
    </div>
    <div class="table-scroll">
    <table>
      <thead><tr><th>Driver</th><th title="Track-limit cutting warnings issued">Warnings</th><th>Penalties</th><th title="Collisions with other cars or the environment">Crashes</th><th title="Added to final time for penalties not served on track">Time penalty</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
  </div>"""


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result_json", nargs="?", help="Path to a server/results/*.json file")
    ap.add_argument("--out", default=None, help="Output directory (default: alongside this script, in 'out/<session name>')")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    results_dir = script_dir.parent / "results"

    if args.result_json:
        result_path = Path(args.result_json)
    else:
        candidates = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise SystemExit(f"No result JSON files found in {results_dir}")
        result_path = candidates[-1]

    data = load(result_path)
    classification, laps_df, max_laps = build_tables(data)
    sector_bests = compute_sector_bests(laps_df, classification)
    if not laps_df.empty:
        laps_df = compute_positions(laps_df)

    title = track_title(data)
    session_label = f"{title} — {data.get('Type', 'Session')}"

    out_dir = Path(args.out) if args.out else script_dir / "out" / result_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    ac_root = script_dir.parent.parent  # race_reports -> server -> assettocorsa
    server_dir = script_dir.parent
    styles = driver_styles(classification)
    folder, config = track_folder_and_config(data)
    car_thumbs, badges, outline_rel, preview_rel, track_meta = prepare_assets(
        ac_root, classification, styles, folder, config, out_dir)

    penalty_log = find_penalty_log(server_dir, data, result_path)
    incidents = parse_penalty_log(penalty_log) if penalty_log else {}
    pit_stops = build_pit_stops(penalty_log) if penalty_log else {}
    for guid, crashes in build_crash_stats(data).items():
        incidents.setdefault(
            guid, {"warnings": 0, "warning_laps": [], "penalties": [], "time_penalty_s": 0})
        incidents[guid]["crashes"] = crashes
    car_thumbs_abs = {k: out_dir / v for k, v in car_thumbs.items()}
    outline_abs = out_dir / outline_rel if outline_rel else None

    render_podium_png(classification, session_label, out_dir / "podium.png",
                        car_thumbs=car_thumbs_abs, outline_path=outline_abs)
    if not laps_df.empty:
        laps_df = laps_df.copy()
        laps_df["LapTime_s"] = laps_df["LapTime"] / 1000.0
        render_line_chart_png(laps_df, classification, "LapTime_s", "Race pace", "Lap time (s)",
                                out_dir / "pace.png", min_zero=True)
        render_line_chart_png(laps_df, classification, "gap_s", "Gap to leader", "Gap (s)",
                                out_dir / "gaps.png", min_zero=True)
        render_line_chart_png(laps_df, classification, "position", "Position by lap", "Position",
                                out_dir / "positions.png", invert_y=True)
    if not laps_df.empty:
        render_tyre_strategy_png(laps_df, classification, "Tyre strategy", out_dir / "tyres.png")

    render_html(data, classification, laps_df, session_label, out_dir / "report.html",
                 car_thumbs=car_thumbs, badges=badges, outline_rel=outline_rel,
                 preview_rel=preview_rel, track_meta=track_meta, sector_bests=sector_bests,
                 incidents=incidents, pit_stops=pit_stops)

    print(f"Done. Output in: {out_dir}")
    for f in sorted(out_dir.glob("*")):
        print(" -", f.name)


if __name__ == "__main__":
    main()
