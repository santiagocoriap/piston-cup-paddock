"""The race setup that the server collector writes into the Content Manager preset (phase 4 of
docs/plans/ac-integration.md, and docs/adr/0002-collector-automation.md).

An admin clicks "Enviar al servidor" on the round page. The app makes the content: one entry
for each driver, with the ballast and the restrictor of the round, the track, the announced
conditions, and the Paddock script with a new race code. The collector asks for work every 30
seconds. It writes the files only while the AC server is stopped, and it keeps a copy of the
old files first. The collector never starts or stops the server: an admin does it.
"""

import re

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.common.urls import is_local
from apps.competition.models import Round
from apps.handicaps.services import assigned_values
from apps.telemetry import script

from .models import CollectorToken, ServerPush

# An AC weather name, such as "3_clear" or "sol_05_broken_clouds". A free text such as
# "Despejado" cannot go into the server.
WEATHER_ID = re.compile(r"^(sol_)?\d+_[a-z0-9_]+$")
# A car, track, or layout key: a folder name of AC. Other text cannot go into the server files.
SAFE_KEY = re.compile(r"^[A-Za-z0-9_.\-]*$")
STEAM_ID = re.compile(r"^\d{17}$")
# A Content Manager preset folder, for example "SERVER_01" or "Rain Piston".
PRESET_FOLDER = re.compile(r"^[A-Za-z0-9_\-][A-Za-z0-9 _.\-()]{0,99}$")
# The steps of the collector that the app accepts.
REPORTS = {ServerPush.State.WAITING, ServerPush.State.DONE, ServerPush.State.FAILED}


class SetupError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sun_angle(time_of_day: str) -> int | None:
    """The AC sun angle of a clock time: 13:00 is 0, and one hour is 16 degrees."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", time_of_day or "")
    if not match:
        return None
    minutes = int(match[1]) * 60 + int(match[2])
    return max(-80, min(80, round((minutes - 13 * 60) * 16 / 60)))


def _clean(text) -> str:
    """A name or a team for one line of the server files: no line breaks, no control
    characters, and no quotes."""
    return re.sub(r"[\x00-\x1f\x7f']", " ", str(text or "")).strip()[:100]


def _key(value: str) -> str:
    if not SAFE_KEY.match(value or ""):
        raise SetupError("unsafe_key")
    return value


def _number(value) -> int | None:
    match = re.search(r"-?\d+", str(value if value is not None else ""))
    return int(match[0]) if match else None


def conditions(announced: dict) -> dict:
    """The announced conditions as server values. A value that the server cannot take is not in
    the result: the collector keeps the value of the preset."""
    found: dict = {}
    angle = sun_angle(announced.get("time_of_day") or "")
    if angle is not None:
        found["sun_angle"] = angle
    air = announced.get("air_temp_c")
    if isinstance(air, int):
        found["air_temp_c"] = air
        track = announced.get("track_temp_c")
        if isinstance(track, int):
            # In server_cfg.ini, the road temperature is the difference from the air.
            found["road_offset_c"] = track - air
    grip = _number(announced.get("grip"))
    if grip is not None and 50 <= grip <= 100:
        found["grip_pct"] = grip
    weather = str(announced.get("weather") or "").strip()
    if WEATHER_ID.match(weather):
        found["weather"] = weather
    return found


def build(round_: Round, base_url: str, open_slots: int | None = None) -> dict:
    """The content of a push, without the race code. The preview shows it before the push.
    open_slots: the free slots after the drivers. None: the setting of the championship."""
    values = assigned_values(round_)
    entries = []
    warnings = []
    for entry in round_.season.entries.select_related("driver", "car", "skin").order_by("number"):
        if entry.car is None:
            # No car yet: the server cannot load the driver. The preview shows the warning.
            warnings.append(f"no_car:{_clean(entry.driver.display_name)}")
            continue
        ballast, restrictor = values.get(entry.id, (0, 0))
        guid = entry.driver.steam_guid or ""
        if not STEAM_ID.match(guid):
            warnings.append(f"no_guid:{_clean(entry.driver.display_name)}")
            guid = ""
        entries.append(
            {
                "number": entry.number,
                "name": _clean(entry.driver.display_name),
                "team": _clean(entry.team),
                "guid": guid,
                "model": _key(entry.car.key),
                "skin": entry.skin.key if entry.skin else "",
                "ballast_kg": ballast,
                "restrictor_pct": restrictor,
            }
        )
    if not entries:
        raise SetupError("no_entries")
    layout = round_.track_layout
    announced = round_.announced_conditions or {}
    weather = str(announced.get("weather") or "").strip()
    if weather and not WEATHER_ID.match(weather):
        warnings.append("weather_kept")
    if is_local(base_url):
        # The game of every other driver looks for the script on its own computer.
        warnings.append("local_address")
    return {
        "round": {"id": round_.id, "number": round_.number},
        "track": {"key": _key(layout.track.key), "layout": _key(layout.key)},
        "entries": entries,
        "conditions": conditions(announced),
        "open_slots": round_.season.championship.open_slots if open_slots is None else open_slots,
        "script": {"url": f"{base_url}/api/script/paddock.lua"},
        "warnings": warnings,
    }


def server_presets(championship) -> tuple[list[dict], str]:
    """The presets of the server and the preset in use, from the collector seen last."""
    token = (
        championship.collectors.filter(revoked_at__isnull=True)
        .exclude(presets=[])
        .order_by("-last_seen_at")
        .first()
    )
    return (token.presets, token.preset) if token else ([], "")


def save_presets(token: CollectorToken, presets: list[dict], current: str) -> None:
    clean = []
    for item in presets[:50]:
        folder = str(item.get("folder") or "")
        if PRESET_FOLDER.match(folder):
            clean.append({"folder": folder, "name": _clean(item.get("name")) or folder})
    folders = {item["folder"] for item in clean}
    token.presets = clean
    token.preset = current if current in folders else ""
    token.save(update_fields=["presets", "preset"])


def push(
    round_: Round,
    user,
    base_url: str,
    open_slots: int | None = None,
    preset: str | None = None,
) -> ServerPush:
    """Make a push for the collector. A newer push replaces a push that waits. preset: the
    folder of another Content Manager preset. None: the preset that the collector uses."""
    content = build(round_, base_url, open_slots)
    championship = round_.season.championship
    if preset:
        known, _current = server_presets(championship)
        if preset not in {item["folder"] for item in known}:
            raise SetupError("unknown_preset")
        content["preset"] = preset
    with transaction.atomic():
        code = script.new_code(championship, user)
        content["script"]["race_code"] = code.code
        championship.server_pushes.filter(
            status__in=[ServerPush.State.PENDING, ServerPush.State.WAITING]
        ).update(status=ServerPush.State.CANCELLED, finished_at=timezone.now())
        item = ServerPush.objects.create(
            championship=championship, round=round_, content=content, requested_by=user
        )
        record(
            user,
            "server.push_requested",
            "round",
            round_.id,
            championship=championship,
            params={"number": round_.number, "entries": len(content["entries"])},
        )
    return item


def next_command(token: CollectorToken) -> ServerPush | None:
    """The push that waits for this collector, the oldest first."""
    return (
        token.championship.server_pushes.filter(
            status__in=[ServerPush.State.PENDING, ServerPush.State.WAITING]
        )
        .order_by("requested_at")
        .first()
    )


def report(token: CollectorToken, push_id: int, status: str, error: str) -> ServerPush:
    item = token.championship.server_pushes.filter(pk=push_id).first()
    if item is None:
        raise SetupError("unknown_push")
    if status not in REPORTS:
        raise SetupError("unknown_status")
    if item.status not in (ServerPush.State.PENDING, ServerPush.State.WAITING):
        return item  # A cancelled or finished push stays as it is.
    item.status = status
    item.error = error[:100]
    item.collector = token
    fields = ["status", "error", "collector"]
    if status in (ServerPush.State.DONE, ServerPush.State.FAILED):
        item.finished_at = timezone.now()
        fields.append("finished_at")
    with transaction.atomic():
        item.save(update_fields=fields)
        if status in (ServerPush.State.DONE, ServerPush.State.FAILED):
            record(
                None,
                f"server.push_{status}",
                "round",
                item.round_id,
                championship=token.championship,
                params={"number": item.round.number, "error": item.error, "collector": token.name},
            )
    return item
