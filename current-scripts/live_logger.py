#!/usr/bin/env python3
"""Standalone Assetto Corsa UDP plugin that logs live car positions during a
race, for later replay with render_replay.py.

Implements the official ACSP UDP plugin protocol directly (opcodes and
packet layouts taken from Kunos' own SDK sample, shipped with the game at
sdk/dev/acRemoteServerUDP_Example/.../ACSProtocol.cs and Program.cs) --
no external AC-specific library needed.

This is NOT retroactive: it only captures races run *while this script is
running and wired in*. Existing server/results/*.json files have no
continuous position data, so past races can't be replayed.

--- Wiring it into Content Manager -----------------------------------------
Same "Extra plugins" mechanism already used for RealPenalty on this server
(Advanced tab -> CM plugin -> Extra plugins -> Add new plugin):
  Address:    127.0.0.1:<--listen-port, e.g. 6972>
  Local port: <--reply-port, default 6968, same as the server's own
               UDP_PLUGIN_LOCAL_PORT -- every plugin's replies funnel back
               to that one port, same as RealPenalty's UDP_RESPONSE>
Then start this script (python live_logger.py) before or after the server,
same as RealPenalty's own ac_penalty.exe -- it doesn't need to be running
first.
-----------------------------------------------------------------------------

Arguments:
    --listen-port INT (default 6972)
        UDP port this logger listens on. Put this in Content Manager's Extra
        plugin "Address" field as 127.0.0.1:<listen-port>.
    --reply-port INT (default 6966)
        Port this logger sends commands/replies to -- the server's own
        UDP_PLUGIN_LOCAL_PORT from server_cfg.ini. Same port RealPenalty's
        UDP_RESPONSE points at; every plugin's replies funnel back to it.
    --out-dir PATH (default ./telemetry next to this script)
        Directory where per-session positions.csv/laps.csv/crashes.csv and
        meta.json are written.

    --restart-on-heavy-damage (flag, default off)
        Arms the auto-restart watchdog described below. Off by default --
        with it unset, none of the other --heavy-damage-*/--restart-* flags
        do anything.
    --heavy-damage-kmh FLOAT (default 60.0)
        Impact speed, in km/h, that a CLIENT_EVENT collision (car-to-car or
        car-to-env) must reach for that car to count as "heavily damaged".
        There's no real per-car damage value available over the stock ACSP
        protocol (confirmed RealPenalty doesn't log one either), so impact
        speed is used as a stand-in.
    --heavy-damage-fraction FLOAT (default 0.9)
        Fraction of the grid (every car_id seen connected this session) that
        must be heavily damaged before a restart is armed.
    --restart-window-seconds FLOAT (default 60.0)
        The heavy-damage check only arms within this many seconds of the
        session starting. Past this, no restart is armed no matter how much
        of the grid is damaged.
    --restart-countdown-seconds FLOAT (default 20.0)
        Delay between arming (chat warning broadcast) and actually sending
        RESTART_SESSION, during which it can still be cancelled.
    --restart-cancel-command STR (default "!cancelrestart")
        Exact chat text (case-insensitive, whitespace-trimmed) that cancels
        a pending restart.
    --restart-admin-guids STR (default "<ADMIN_STEAM_GUID>", comma-separated)
        steamID64 GUIDs allowed to send the cancel command. Defaults to the
        admin GUID already configured in RealPenalty's ac_settings.ini. Set
        to an empty string ("") to let any connected driver cancel.

Behavior of the watchdog once --restart-on-heavy-damage is set: only ever
arms during Race sessions -- Practice/Qualify are never affected, no matter
how many cars crash. Once armed it broadcasts a chat warning and fires the
native ACSP RESTART_SESSION (208) UDP opcode after the countdown, unless an
admin cancels it first; a manual cancel is one-shot and won't re-arm for the
rest of that session.
"""
import argparse
import csv
import functools
import io
import socket
import struct
import sys
import time
from pathlib import Path

print = functools.partial(print, flush=True)  # status lines show up immediately, not buffered

# --- ACSP opcodes (byte values), from ACSProtocol.cs ------------------------
NEW_SESSION = 50
NEW_CONNECTION = 51
CONNECTION_CLOSED = 52
CAR_UPDATE = 53
CAR_INFO = 54
END_SESSION = 55
VERSION = 56
CHAT = 57
CLIENT_LOADED = 58
SESSION_INFO = 59
ERROR = 60
LAP_COMPLETED = 73
CLIENT_EVENT = 130
REALTIMEPOS_INTERVAL = 200
GET_CAR_INFO = 201
SEND_CHAT = 202
BROADCAST_CHAT = 203
GET_SESSION_INFO = 204
SET_SESSION_INFO = 205
KICK_USER = 206
NEXT_SESSION = 207
RESTART_SESSION = 208
ADMIN_COMMAND = 209

CE_COLLISION_WITH_CAR = 10
CE_COLLISION_WITH_ENV = 11


class Reader:
    """Little-endian binary reader matching the C# BinaryReader calls in
    the official SDK example byte-for-byte."""

    def __init__(self, data: bytes):
        self.buf = io.BytesIO(data)

    def byte(self):
        b = self.buf.read(1)
        return b[0] if b else 0

    def uint16(self):
        return struct.unpack("<H", self.buf.read(2))[0]

    def int16(self):
        return struct.unpack("<h", self.buf.read(2))[0]

    def uint32(self):
        return struct.unpack("<I", self.buf.read(4))[0]

    def int32(self):
        return struct.unpack("<i", self.buf.read(4))[0]

    def single(self):
        return struct.unpack("<f", self.buf.read(4))[0]

    def vec3(self):
        return self.single(), self.single(), self.single()

    def string(self):
        n = self.byte()
        return self.buf.read(n).decode("ascii", errors="replace")

    def stringw(self):
        n = self.byte()
        raw = self.buf.read(n * 4)
        return raw.decode("utf-32-le", errors="replace")


def write_stringw(s: str) -> bytes:
    data = s.encode("utf-32-le")
    return bytes([len(s) & 0xFF]) + data


def send_realtimepos_interval(sock, addr, interval_ms=200):
    sock.sendto(struct.pack("<BH", REALTIMEPOS_INTERVAL, interval_ms), addr)


def send_get_car_info(sock, addr, car_id):
    sock.sendto(struct.pack("<BB", GET_CAR_INFO, car_id), addr)


def send_restart_session(sock, addr):
    sock.sendto(bytes([RESTART_SESSION]), addr)


def send_broadcast_chat(sock, addr, message):
    sock.sendto(bytes([BROADCAST_CHAT]) + write_stringw(message), addr)


class SessionLog:
    """One CSV per session: positions.csv (continuous) + laps.csv (markers),
    plus a meta.json sidecar so render_replay.py can find the right track
    assets and driver names without guessing."""

    def __init__(self, out_dir: Path, session_name: str, track, track_config, session_type,
                 session_time_min=0, session_laps=0):
        out_dir.mkdir(parents=True, exist_ok=True)
        self.session_name = session_name
        self.track, self.track_config, self.session_type = track, track_config, session_type
        self.session_time_min, self.session_laps = session_time_min, session_laps
        self.pos_path = out_dir / f"{session_name}_positions.csv"
        self.lap_path = out_dir / f"{session_name}_laps.csv"
        self.crash_path = out_dir / f"{session_name}_crashes.csv"
        self.meta_path = out_dir / f"{session_name}_meta.json"
        self.pos_file = open(self.pos_path, "w", newline="", encoding="utf-8")
        self.lap_file = open(self.lap_path, "w", newline="", encoding="utf-8")
        self.crash_file = open(self.crash_path, "w", newline="", encoding="utf-8")
        self.pos_writer = csv.writer(self.pos_file)
        self.lap_writer = csv.writer(self.lap_file)
        self.crash_writer = csv.writer(self.crash_file)
        self.pos_writer.writerow(["t_ms", "car_id", "x", "y", "z", "norm_pos", "gear", "rpm"])
        self.lap_writer.writerow(["t_ms", "car_id", "lap_time_ms", "cuts"])
        self.crash_writer.writerow(["t_ms", "car_id", "kind", "other_car_id", "impact_speed", "x", "y", "z"])
        self.t0 = time.monotonic()

        # Heavy-damage restart watchdog state, reset fresh for every session.
        self.grid_car_ids = set()     # every car_id seen connected this session
        self.heavy_damaged = set()    # car_ids with at least one impact over the threshold
        self.restart_fire_at = None   # elapsed_ms() deadline, or None if no countdown running
        self.restart_resolved = False  # True once this session has fired or been cancelled once

    def elapsed_ms(self):
        return int((time.monotonic() - self.t0) * 1000)

    def car_update(self, car_id, x, y, z, norm_pos, gear, rpm):
        self.pos_writer.writerow([self.elapsed_ms(), car_id, f"{x:.2f}", f"{y:.2f}",
                                    f"{z:.2f}", f"{norm_pos:.4f}", gear, rpm])

    def lap_completed(self, car_id, laptime_ms, cuts):
        self.lap_writer.writerow([self.elapsed_ms(), car_id, laptime_ms, cuts])

    def crash_event(self, car_id, kind, other_car_id, speed, x, y, z):
        self.crash_writer.writerow([self.elapsed_ms(), car_id, kind,
                                      other_car_id if other_car_id is not None else "",
                                      f"{speed:.2f}", f"{x:.2f}", f"{y:.2f}", f"{z:.2f}"])

    def write_meta(self, drivers):
        import json
        meta = {
            "session_name": self.session_name,
            "track": self.track,
            "track_config": self.track_config,
            "session_type": self.session_type,
            "session_time_min": self.session_time_min,
            "session_laps": self.session_laps,
            "drivers": {str(cid): {"name": n, "guid": g, "model": m}
                         for cid, (n, g, m) in drivers.items()},
        }
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def flush(self):
        self.pos_file.flush()
        self.lap_file.flush()
        self.crash_file.flush()

    def close(self):
        self.pos_file.close()
        self.lap_file.close()
        self.crash_file.close()


def safe_name(s):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)[:60]


class RestartWatchdog:
    """Config for the heavy-damage auto-restart. Only ever acts on Race
    sessions -- Practice/Qualify never arm or fire this, no matter how many
    cars crash. There's no real damage value available over ACSP (confirmed:
    RealPenalty doesn't log one either), so a hard impact (CLIENT_EVENT speed
    over the threshold) is used as a stand-in for "heavy damage"."""

    def __init__(self, heavy_damage_kmh, heavy_damage_fraction, window_seconds,
                 countdown_seconds, cancel_command, admin_guids):
        self.heavy_damage_kmh = heavy_damage_kmh
        self.heavy_damage_fraction = heavy_damage_fraction
        self.window_seconds = window_seconds
        self.countdown_seconds = countdown_seconds
        self.cancel_command = cancel_command
        self.admin_guids = admin_guids  # empty set = any connected driver can cancel


def note_impact(sock, reply_addr, log, watchdog, car_id, speed_ms):
    """Called on every CLIENT_EVENT. Arms the restart countdown once enough
    of the grid has taken a hard hit, early enough in a Race session."""
    if watchdog is None or log.session_type.lower() != "race":
        return
    if log.restart_resolved or log.restart_fire_at is not None:
        return  # already fired/cancelled, or a countdown is already running
    if log.elapsed_ms() > watchdog.window_seconds * 1000:
        return

    if speed_ms * 3.6 >= watchdog.heavy_damage_kmh:
        log.heavy_damaged.add(car_id)

    grid_size = len(log.grid_car_ids)
    if grid_size == 0:
        return
    if len(log.heavy_damaged) / grid_size >= watchdog.heavy_damage_fraction:
        arm_restart_countdown(sock, reply_addr, log, watchdog)


def arm_restart_countdown(sock, reply_addr, log, watchdog):
    log.restart_fire_at = log.elapsed_ms() + watchdog.countdown_seconds * 1000
    msg = (f"RACE CONTROL: {len(log.heavy_damaged)}/{len(log.grid_car_ids)} cars heavily damaged -- "
           f"restarting session in {watchdog.countdown_seconds}s. "
           f"Admin: type {watchdog.cancel_command} in chat to cancel.")
    print(msg)
    send_broadcast_chat(sock, reply_addr, msg)


def check_restart_deadline(sock, reply_addr, log, watchdog):
    if log.restart_fire_at is None or log.elapsed_ms() < log.restart_fire_at:
        return
    print("RESTART_SESSION sent (heavy-damage watchdog).")
    send_broadcast_chat(sock, reply_addr, "RACE CONTROL: restarting session now.")
    send_restart_session(sock, reply_addr)
    log.restart_fire_at = None
    log.restart_resolved = True


def handle_chat_for_restart(sock, reply_addr, log, watchdog, drivers, car_id, message):
    if watchdog is None or log is None or log.restart_fire_at is None:
        return
    if message.strip().lower() != watchdog.cancel_command.lower():
        return
    driver_name, driver_guid, _ = drivers.get(car_id, ("unknown", None, None))
    if watchdog.admin_guids and driver_guid not in watchdog.admin_guids:
        print(f"Ignored restart-cancel from non-admin: {driver_name} (GUID {driver_guid})")
        return

    log.restart_fire_at = None
    log.restart_resolved = True  # one-shot: a manual cancel doesn't re-arm this session
    msg = f"RACE CONTROL: restart cancelled by {driver_name}."
    print(msg)
    send_broadcast_chat(sock, reply_addr, msg)


def run(listen_port, reply_port, out_dir, restart_watchdog=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", listen_port))
    sock.settimeout(1.0)  # wake up periodically even with no traffic, to check a pending restart countdown
    reply_addr = ("127.0.0.1", reply_port)
    print(f"live_logger listening on 0.0.0.0:{listen_port}, replying to 127.0.0.1:{reply_port}")
    print(f"Telemetry will be written under: {out_dir}")
    if restart_watchdog:
        print(f"Restart watchdog armed: {restart_watchdog.heavy_damage_fraction:.0%} of grid at "
              f">={restart_watchdog.heavy_damage_kmh:.0f}km/h impact within {restart_watchdog.window_seconds}s "
              f"of a Race session -> {restart_watchdog.countdown_seconds}s warning, cancel with "
              f"'{restart_watchdog.cancel_command}' in chat")

    drivers = {}       # car_id -> (name, guid, model)
    log = None
    last_flush = time.monotonic()

    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            if log:
                check_restart_deadline(sock, reply_addr, log, restart_watchdog)
            continue
        except (ConnectionResetError, OSError):
            # Windows raises WSAECONNRESET on recvfrom after a prior sendto
            # to a closed remote port -- harmless for a UDP listener, ignore.
            continue
        if not data:
            continue
        r = Reader(data)
        packet_id = r.byte()

        try:
            if packet_id == VERSION:
                proto_version = r.byte()
                print(f"Server protocol version: {proto_version}")

            elif packet_id in (NEW_SESSION, SESSION_INFO):
                r.byte()  # protocol version
                r.byte()  # session index
                r.byte()  # current session index
                r.byte()  # session count
                r.stringw()  # server name
                track = r.string()
                track_config = r.string()
                name = r.string()
                r.byte()  # type
                session_time_min = r.uint16()  # 0 if this session isn't time-limited
                session_laps = r.uint16()  # 0 if this session isn't lap-limited
                r.uint16()  # wait time
                r.byte()  # ambient temp
                r.byte()  # road temp
                r.string()  # weather graphics
                r.int32()  # elapsed ms

                if packet_id == NEW_SESSION:
                    if log:
                        log.write_meta(drivers)
                        log.flush()
                        log.close()
                    session_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_name(track)}_{safe_name(name)}"
                    log = SessionLog(out_dir, session_name, track, track_config, name,
                                       session_time_min, session_laps)
                    log.grid_car_ids = set(drivers.keys())  # seed with whoever's already connected
                    log.write_meta(drivers)  # partial roster now; rewritten as drivers connect
                    print(f"New session: {name} @ {track} ({track_config}) -> {session_name}")
                    send_realtimepos_interval(sock, reply_addr, 200)

            elif packet_id == CAR_UPDATE:
                car_id = r.byte()
                x, y, z = r.vec3()
                r.vec3()  # velocity, not needed for a 2D replay
                gear = r.byte()
                rpm = r.uint16()
                norm_pos = r.single()
                if log:
                    log.car_update(car_id, x, y, z, norm_pos, gear, rpm)

            elif packet_id == NEW_CONNECTION:
                driver_name = r.stringw()
                driver_guid = r.stringw()
                car_id = r.byte()
                car_model = r.string()
                r.string()  # car skin
                drivers[car_id] = (driver_name, driver_guid, car_model)
                print(f"Connected: car {car_id} = {driver_name} ({car_model})")
                if log:
                    log.grid_car_ids.add(car_id)
                    log.write_meta(drivers)

            elif packet_id == CONNECTION_CLOSED:
                r.stringw(); r.stringw()
                car_id = r.byte()
                r.string(); r.string()
                drivers.pop(car_id, None)

            elif packet_id == LAP_COMPLETED:
                car_id = r.byte()
                laptime = r.uint32()
                cuts = r.byte()
                if log:
                    log.lap_completed(car_id, laptime, cuts)
                cars_count = r.byte()
                for _ in range(cars_count):
                    r.byte(); r.uint32(); r.uint16(); r.byte()
                r.single()  # grip level

            elif packet_id == END_SESSION:
                filename = r.stringw()
                print(f"Session ended, AC report: {filename}")
                if log:
                    log.write_meta(drivers)
                    log.flush()

            elif packet_id == ERROR:
                print("ACSP_ERROR:", r.stringw())

            elif packet_id == CLIENT_EVENT:
                ev_type = r.byte()
                car_id = r.byte()
                other_car_id = r.byte() if ev_type == CE_COLLISION_WITH_CAR else None
                speed = r.single()
                x, y, z = r.vec3()
                r.vec3()  # position relative to the other car/env, not needed for a map marker
                if log:
                    kind = "car" if ev_type == CE_COLLISION_WITH_CAR else "env"
                    log.crash_event(car_id, kind, other_car_id, speed, x, y, z)
                    note_impact(sock, reply_addr, log, restart_watchdog, car_id, speed)

            elif packet_id == CHAT:
                car_id = r.byte()
                message = r.stringw()
                handle_chat_for_restart(sock, reply_addr, log, restart_watchdog, drivers, car_id, message)

            # CLIENT_LOADED, CAR_INFO are received but not needed for
            # position replay -- skip without parsing.

        except (struct.error, IndexError):
            # A malformed/short packet shouldn't take the logger down.
            continue

        if log:
            check_restart_deadline(sock, reply_addr, log, restart_watchdog)
            if time.monotonic() - last_flush > 5:
                log.flush()
                last_flush = time.monotonic()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen-port", type=int, default=6972,
                      help="UDP port this logger listens on (put this in CM's Extra plugin Address field). Default 6972.")
    ap.add_argument("--reply-port", type=int, default=6966,
                      help="Port to send commands to -- the server's UDP_PLUGIN_LOCAL_PORT. Default 6968.")
    ap.add_argument("--out-dir", default=None, help="Telemetry output directory (default: ./telemetry)")

    ap.add_argument("--restart-on-heavy-damage", action="store_true",
                      help="Arm the auto-restart watchdog (Race sessions only).")
    ap.add_argument("--heavy-damage-kmh", type=float, default=60.0,
                      help="Impact speed (km/h) in a CLIENT_EVENT collision that counts as 'heavy damage' "
                           "for that car. Default 60. There's no real damage value over ACSP, so this is a "
                           "stand-in -- RealPenalty's own logs don't record one either.")
    ap.add_argument("--heavy-damage-fraction", type=float, default=0.9,
                      help="Fraction of the grid that must be heavily damaged to arm a restart. Default 0.9.")
    ap.add_argument("--restart-window-seconds", type=float, default=60.0,
                      help="Only arms within this many seconds of session start. Default 60.")
    ap.add_argument("--restart-countdown-seconds", type=float, default=20.0,
                      help="Warning time (seconds) between arming and actually restarting, during which "
                           "it can be cancelled from chat. Default 20.")
    ap.add_argument("--restart-cancel-command", default="!cancelrestart",
                      help="Chat text that cancels a pending restart. Default '!cancelrestart'.")
    ap.add_argument("--restart-admin-guids", default="<ADMIN_STEAM_GUID>",
                      help="Comma-separated steamID64 GUIDs allowed to cancel a pending restart "
                           "(defaults to the admin GUID already configured in RealPenalty's "
                           "ac_settings.ini). Set to an empty string to let any connected driver cancel.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parent / "telemetry"

    restart_watchdog = None
    if args.restart_on_heavy_damage:
        admin_guids = {g.strip() for g in args.restart_admin_guids.split(",") if g.strip()}
        restart_watchdog = RestartWatchdog(
            heavy_damage_kmh=args.heavy_damage_kmh,
            heavy_damage_fraction=args.heavy_damage_fraction,
            window_seconds=args.restart_window_seconds,
            countdown_seconds=args.restart_countdown_seconds,
            cancel_command=args.restart_cancel_command,
            admin_guids=admin_guids,
        )

    try:
        run(args.listen_port, args.reply_port, out_dir, restart_watchdog)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
