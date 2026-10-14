# 0002 Collector automation

Date: October 14, 2026

Status: Accepted

## Context

The server collector reads the result files, the Real Penalty logs, and the UDP events, and sends them to the app. After that, an admin still does these tasks by hand:

- Apply each import preview.
- Type the conditions of each round.
- Copy the ballast and restrictor of each driver into the AC server before each race.
- Mark each DNF.

The goal of the league owner is an app that needs as little manual work as possible.

The development plan puts "control of the race server" out of scope, and the collector only reads. This record changes both rules in a limited way.

## Decision

1. **The app publishes a clean import automatically.** When a collector file matches one round and the preview has no blocking warning, the app applies it. The result is provisional. An admin still approves the official result. A preview with a blocking warning waits for an admin, as before.
2. **The collector can write three server files.** It writes `entry_list.ini`, some keys of `server_cfg.ini`, and the Paddock section of the CSP options in the welcome message (the script address and the race code), with these limits:
   - An admin starts each write with "Enviar al servidor" in the app.
   - The collector writes only while the AC server is stopped.
   - The collector keeps a copy of each file before it writes.
   - The setting `write_server_config` is off by default. The server owner turns it on.
   - The collector never starts, stops, or restarts the AC server. It never sends a command to the server, other than the existing request for car positions.
3. **Drivers install nothing for league races.** The league server sends a CSP Lua script to each driver who joins, through the CSP options in the welcome message. Phase 0 confirmed that this works. The script sends the telemetry of each lap from inside AC. A race code from the app and the Steam ID of the driver replace the driver key for these laps.
4. **The keys stay as they are.** A server key works for one championship. It can read the server data of that championship and send files and events. It cannot choose users, seasons, or admin actions.

## Consequences

- A race night with no problem needs no admin action until the official approval.
- The ballast and restrictor in the server come from the app. The import check `handicap_differs` shows when the server used other values.
- A bad write can stop the server from starting. The copy of the old file lets the owner go back in one step.
- The audit log records "collector" as the actor of an automatic import and of each server write.
