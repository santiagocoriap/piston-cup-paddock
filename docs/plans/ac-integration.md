# Assetto Corsa integration plan

Date: October 14, 2026

Status: Approved. The decisions are in `docs/adr/0002-collector-automation.md`.

## Goal

A race night needs no upload and no typing. The data goes from the AC server to the app by itself. An admin only checks the problems and approves the official result.

## The driver installs nothing

A driver program that the driver must open is not reliable: people forget it. A program that starts with Windows is also not good enough. So the plan does not use the Python driver collector for league races.

The league server already needs Custom Shaders Patch (CSP): the result files show the `csp/` prefix in the track name. CSP lets a server send a Lua script to every driver who joins. The server lists the script in its CSP options:

```ini
[SCRIPT_1]
SCRIPT = 'https://<app address>/collector/paddock.lua'
raceCode = '<race code from the app>'
```

On the league server, Content Manager puts the CSP options inside the welcome message file, as a hidden `$CSP0:` block (zlib, then base64, after 32 tab characters). The server collector must write the script section into that block. Phase 0 confirmed this format.

When a driver joins the league server, AC downloads the script and runs it inside the game. The script stops when the driver leaves. The driver installs nothing and opens nothing. Each lap goes to the app from inside AC.

What the script does:

1. Reads the speed, track position, pedals, steering, gear, and RPM of the player car on each frame.
2. At the end of each lap, sends the lap to the app with `web.request`.
3. Sends the Steam ID of the driver and the race code (see below) with each lap. The script reads the race code from its section with `ac.configValues`.
4. Shows a small line in AC: "Paddock: grabando". The driver can see that it works.

How the app trusts a lap without a driver key:

- When the admin clicks "Enviar al servidor", the app makes a new race code. The server collector writes it in the `$CSP0:` block of the welcome message, in the script section. Only drivers on the server get it.
- The app takes a lap only when the race code is the current one, and the server collector shows that this Steam ID was connected at that time.
- Every driver on the server gets the race code, so a driver could send a lap with the Steam ID of another driver. So the server is also the witness of each lap: the app takes a lap only when the server recorded a lap for this Steam ID with the same lap time (50 ms or less of difference). Only the first upload of a server lap counts.

Practice outside the league (optional, later): CSP also has Lua apps that load with AC every time, after the driver turns them on one time. A "Paddock práctica" app can send private practice laps. It is not needed for league races.

## What exists today

| Part | What it does | Where |
| --- | --- | --- |
| Server collector | Sends result files, Real Penalty logs, and UDP events | `collector/paddock_collector.py` |
| Driver collector (removed on October 14, 2026) | Sent the telemetry of each lap of one driver. Linked a lap to a round only by track and time | The Paddock script replaces it |
| Collector API | Ping, files, events, with a key for each championship | `backend/apps/collectors/api.py` |
| Round match | Finds the round from the track and the session time | `backend/apps/collectors/services.py` |
| Import preview | Matches drivers by GUID, and shows warnings | `backend/apps/imports/services.py` |
| Penalty preview | Finds restarts and penalties in the Real Penalty logs | `backend/apps/imports/penalty_services.py` |
| Assigned handicaps | The ballast and restrictor of each entry for a round | `backend/apps/handicaps/services.py` |
| Conditions draw | The announced conditions of a round | `ConditionsDraw` in `backend/apps/competition/models.py` |

## Manual work that the plan removes

| Manual task today | Phase that removes it |
| --- | --- |
| An admin applies each import preview | 1 |
| An admin moves a driver lap that the app linked to the wrong round | 2 |
| An admin types the conditions | 3 |
| An admin marks each DNF | 3 (a suggestion, the admin confirms) |
| An admin copies the ballast and restrictor into the server | 4 |
| An admin copies the track and the weather into the server | 4 |
| The owner installs Python and makes a Windows task | 5 |
| Each driver installs and opens a program | 0 and 2 (the server sends a script) |
| Nobody sees when a collector stops | 6 |

## Phase 0: Test the script idea

Status: done on October 14, 2026. All 4 points pass.

Estimate: half a day. Do this first, because phases 2 and 5 depend on it.

### Result

The test used a local AC server with its own config, CSP 0.2.11-preview1, and a test script, `collector/script/paddock_test.lua` (removed after phase 2).

| Point | Result |
| --- | --- |
| AC runs the script with no driver action | Pass. The CSP log shows "Server Script: SCRIPT_1 loaded and ready to run" |
| `web.post` reaches the app | Pass. One request at start, and one request with the samples at each lap |
| The script reads the Steam ID | Pass. `ac.getUserSteamID()` gives the 17-digit Steam ID |
| The script reads the race code | Pass. `ac.configValues({ raceCode = '' })` reads the value from the script section |
| The script does not slow the game | Pass. About 0.002 ms for each frame, at 217 FPS |

Other findings:

- The section name must be `[SCRIPT_1]`, `[SCRIPT_2]`, and so on. A first try with `[SCRIPT_PADDOCK]` loaded nothing, and the CSP log showed no error.
- The script address accepts parameters. `{SteamID}` in the address became the real Steam ID.
- One lap of 114 seconds at 20 samples each second is about 2,170 samples and 70 KB of JSON. Phase 2 can compress it.
- CSP allows two web requests at the same time. The script sends one at a time, from a queue.
- `ac.onLapCompleted` gives the lap time, the cut count, and the valid flag. These matched the AC server.
- An `http://` address on the same PC worked. The real app uses `https://`.

1. Write a small test script that shows a line in AC and sends one request to the app at each lap.
2. Put it in `csp_extra_options.ini` of a test server.
3. Join the server with CSP and check these 4 points:
   - AC runs the script with no action from the driver.
   - `web.request` can reach the app. The CSP safety rules block files and system calls, but the SDK does not show a block for web requests.
   - The script can read the Steam ID of the player.
   - The script does not change the frame rate.
4. If a point fails, the fallback is the driver program from phase 5, started by the Content Manager setting for a command before the race.

## Phase 1: Publish clean imports automatically

Status: done on October 14, 2026. The code is in `backend/apps/imports/auto_publish.py`, and the tests are in `backend/tests/test_auto_publish.py`.

Estimate: 1 day.

### Result files

1. After `receive_file` makes the preview, run a new task `auto_apply(result_import)` in the worker.
2. The task applies the import only when all of these are true:
   - The file matched exactly one round.
   - Every GUID in the file has an entry.
   - The preview has no file warning (`track_differs`).
   - No row has `guid_differs_in_result`, `car_differs`, or `handicap_differs`.
3. A row with only `fewer_laps` does not block. The app gives the status "finished" and marks the row "check DNF". Phase 3 makes this mark better.
4. The result is provisional. The protest window starts as it does today.
5. A blocked preview stays in the round page with the reason. The admin sees it in "Qué tenés que hacer".

### Real Penalty logs

1. When the race result file is applied, also apply the race logs of the round:
   - Add the restarts that the logs show.
   - Add the penalties that the driver served in the race.
   - Mark the invalid laps.
2. A penalty "Seconds penalty to final time" waits for an admin. The open question 1 in `docs/DATA_SOURCES.md` says why.

### App changes

- A championship setting "Publicar resultados automáticamente", on by default.
- The audit log records the actor "colector".
- A notification to the admins and the drivers: "Resultado provisional publicado".

### Tests

- A clean file publishes a provisional result with no admin.
- Each blocking warning keeps the preview waiting.
- The same file sent two times publishes one time only.
- The setting off keeps the old behavior.

## Phase 2: Session sync and the script

Estimate: 2.5 days.

### The problem

A driver collector sends every lap: offline practice, laps on other servers, and laps in the league race. Today the app links a lap to a round when the track is the same and the time is near the round date (`_find_round` in `backend/apps/telemetry/services.py`). An offline lap on the same track on race day gets the wrong link.

### The rule

The server collector is the source of truth. A driver lap belongs to a league session only when the league server says that the driver was on it at that time. All other laps are private practice.

### Session records in the app

1. A new model `ServerSession`: collector, round (can be empty), session type, attempt, track, layout, start time, end time, and server address.
2. The server collector already sends `NEW_SESSION`, `NEW_CONNECTION`, and `CONNECTION_CLOSED`. The app turns them into:
   - One `ServerSession` for each session.
   - One `SessionPresence` for each connection: GUID, car, connect time, disconnect time.
3. The app finds the round of a session in the same way as for a result file. A session out of a round window is league practice. It links to the season, not to a round.
4. The race attempts of phase 1 link to the sessions. A restart is a new race session on the same round.

### What the script adds to each lap

1. The race code from `csp_extra_options.ini`.
2. The Steam ID of the driver.
3. The car, the track, and the layout.
4. The clock of the driver PC. The app compares it with its own clock and corrects the lap times. A PC clock that is 3 minutes wrong still matches.

### How the app matches a lap

A lap links to a session when all of these are true:

1. The race code is the current code of the championship.
2. The corrected lap time is between the start and the end of a session of that server.
3. The Steam ID has a `SessionPresence` in the session at that time.
4. The track and the car are the same.
5. The server recorded a lap for this Steam ID with the same lap time, at the same time. This stops a driver who sends a lap in the name of another driver.
6. No other upload of the same server lap counts already.

A lap that fails one rule goes nowhere. A lap from the optional practice app is private practice. It stays on the driver page as "Práctica" and never shows in a round. Only its driver sees it.

### Order does not matter

- Laps can come before the server data, for example when the driver PC has no internet during the race.
- When a session ends, the app matches again all laps of that time window that have no session.
- When a late lap comes, the app matches it at once.

### Let every system know

1. A new endpoint `GET /api/telemetry/now` for the script. It gives the league session that runs now, with its track and type.
2. The script asks at the start of each session. The line in AC shows `Paddock: Fecha 3 · Carrera · grabando`. The driver knows at once that the app counts the laps.
3. The round page shows the live state for the admins: the session, the connected drivers, and which drivers send telemetry.

### Driver choices

- The script sends league laps only. The driver chooses who sees them, as today.
- The driver can delete private practice laps from the optional practice app.

### Tests

- An offline lap on race day on the same track stays private.
- A lap on another server stays private.
- A lap on the league server links to the right session and attempt.
- A lap that comes before the session data links when the session ends.
- A PC clock that is 3 minutes wrong still matches.
- A lap with an old race code goes nowhere.
- A lap from a Steam ID that was not connected goes nowhere.

## Phase 3: Read the conditions and the disconnects

Status: done on October 14, 2026. The code is in `backend/apps/collectors/conditions.py` and `backend/apps/collectors/disconnects.py`.

Estimate: 1 day.

What changed from the first idea:

- The weather, the air temperature, and the road temperature come in the UDP `NEW_SESSION` message. The collector does not need a file for them.
- Only the time of day (from `SUN_ANGLE`) and the start grip (from `[DYNAMIC_TRACK] SESSION_START`) come from `server_cfg.ini`. The owner gives its path in `collector.ini` (`server_cfg`). Without it, the app gets the weather and the temperatures only.
- The app reads the conditions on the fly from the collector events, as for the sessions of phase 2. No new table.
- The round page warns when the air is more than 2 °C away, the track more than 3 °C, the time more than 30 minutes, or the grip more than 3 points.
- "Marcar DNF" on the round page changes one line with one click. The result gets a new version with the reason.

### Conditions from the server

1. At each new session (the UDP `NEW_SESSION` event), the collector reads `server_cfg.ini`. The values go to the session record of phase 2.
2. It sends an event `server_config` with these values:
   - `[WEATHER_0] GRAPHICS`, `BASE_TEMPERATURE_AMBIENT`, `BASE_TEMPERATURE_ROAD`
   - `[SERVER] SUN_ANGLE` (the app turns it into a time of day)
   - `[DYNAMIC_TRACK] SESSION_START` (the grip at the start)
   - `TRACK` and `CONFIG_TRACK`
3. The app stores the values as the actual conditions of the session.
4. The round page shows the actual conditions. When they differ from the draw, the page shows a warning.

### DNF suggestions

1. The collector already records the UDP connect and disconnect events.
2. A driver who disconnects before the checkered flag and does not come back gets the suggestion "DNF".
3. A driver with fewer laps who stays connected gets the suggestion "lapped".
4. The admin confirms a DNF with one click on the round page. The app does not change the status by itself.

### Tests

- A `server_config` event fills the actual conditions.
- A difference from the draw shows a warning.
- A disconnect before the end gives a DNF suggestion.

## Phase 4: Send the race setup to the server

Status: done on October 14, 2026. The app part is in `backend/apps/collectors/server_setup.py`, and the collector part is `write_setup` in `collector/paddock_collector.py`.

Estimate: 2 days.

Answers and changes from the first idea:

- The league uses a Content Manager preset, in `server/presets/<name>/`. The collector writes `entry_list.ini`, `server_cfg.ini`, and `csp_extra_options.ini` there. Content Manager makes the `$CSP0:` welcome block from `csp_extra_options.ini` when an admin starts the preset.
- An admin stops the server before the push and starts it after. The collector checks for an `acServer.exe` process and for a busy TCP port. While the server runs, it tells the app "waiting".
- The collector keeps the `csp/<build>/../` prefix of `TRACK`, the Content Manager sections, and the spectator slots of the entry list (for example Race Control).
- After the league drivers, the entry list gets open slots with the league cars in turn, so a driver can change to an extra car. The admins set the number on the championship page (10 by default), and they can change it for one push.
- `BASE_TEMPERATURE_ROAD` is the difference from the air, so the app sends the track temperature minus the air temperature.
- The app sends the weather only when the announced weather is an AC weather name, such as `sol_05_broken_clouds`. Then the preset keeps one weather only. A free text such as "Despejado" keeps the weathers of the preset, and the dialog says so.
- Each push makes a new race code. A newer push replaces a push that waits.
- Risk: if the preset editor of Content Manager is open with old values, a save there can write over the files. Close the preset editor before the push, or open it again after.

### App

1. A new model `ServerPush`: round, requested by, requested at, status (`pending`, `done`, `failed`, `cancelled`), error, and the sent content.
2. On the round page, a new admin action "Enviar al servidor". It shows the content first:
   - The entry list: GUID, driver name, car model, skin, team, ballast, restrictor.
   - The track and layout.
   - The weather, temperatures, and time of day from the conditions draw.
3. A new endpoint `GET /api/collector/commands` gives the pending push of the championship.
4. A new endpoint `POST /api/collector/commands/{id}` gets the result from the collector.

### Collector

1. Every 30 seconds, the collector asks for a pending push.
2. Before it writes, it checks that the AC server is stopped: no `acServer.exe` process, and the server TCP port is free.
3. If the server runs, it reports `server_running` and asks again later.
4. It copies `entry_list.ini` and `server_cfg.ini` to `paddock-backups/` with the date in the name.
5. It writes a new `entry_list.ini`, with one `[CAR_n]` block for each entry, plus the existing extra slots.
6. In `server_cfg.ini`, it changes only `TRACK`, `CONFIG_TRACK`, `SUN_ANGLE`, and the `[WEATHER_0]` keys. It keeps all other lines.
7. In the `$CSP0:` block of the welcome message, it changes only the Paddock script section (address and race code). It keeps all other sections, such as the Real Penalty chat filters and the rain settings.
8. It reports `done`, or `failed` with the reason.
9. The setting `write_server_config = false` is the default. The server owner turns it on in `collector.ini`.

### Checks after the race

- The import check `handicap_differs` already compares the values in the result file with the assigned values. It closes the loop.

### Tests

- The entry list has the right GUID, car, ballast, and restrictor for each entry.
- The collector does not write while the server runs.
- The collector keeps a copy before it writes.
- A failed write reports the error, and the old files stay.

## Phase 5: Install with one click

Status: done on October 14, 2026, for the server collector. The app part is `backend/apps/collectors/release.py`. The build is `.github/workflows/collector.yml`. The first release needs a `collector-v1.1.0` tag.

Estimate: 1.5 to 2 days.

Changes from the first idea:

- The collectors download the new program from the app (`GET /api/collector/download`, with their key), not from GitHub. The app gets it from the newest GitHub release one time and keeps a copy.
- The app keeps only a hash of a key. So "Descargar colector" is available only right after "Crear clave", when the page still has the key.
- The collector does not start with Windows. Content Manager and `acServer.exe` cannot start another program. The admin already starts Real Penalty by hand before each race. So the desktop shortcut "Iniciar Paddock" starts Real Penalty and the collector together, with no new step for the admin.
- The collector stops by itself 15 minutes after the AC server stops, when it sent everything. Without a server, it stops after 6 hours. Only one collector runs on a PC.
- After an update, the collector starts the new program at once and stops.

### Builds

1. A GitHub Actions job builds `paddock-collector.exe` and `paddock-driver.exe` with PyInstaller. Python stays out of the PCs.
2. The app gives the latest builds and their SHA-256 sums: `GET /api/collector/version`.

### Server collector

1. In "Colectores", the button "Crear clave" also offers "Descargar colector". The zip has the `.exe` and a `collector.ini` with the app address and the new key.
2. The command `paddock-collector.exe --install` puts the shortcut "Iniciar Paddock" on the desktop. It starts Real Penalty and the collector.
3. The command `--uninstall` removes the shortcut.

### Drivers

Drivers install nothing for league races: the server sends the script (phase 0 and phase 2). The Python driver collector and its key are removed: the script replaces them.

### Updates

1. Each collector asks for the latest version at each start, and one time a day while it runs.
2. It downloads the new `.exe`, checks the SHA-256 sum, and uses it at the next start.

### Risk

Windows SmartScreen warns about an `.exe` with no code signature. The README tells the user to click "Más información", then "Ejecutar de todas formas". A code signing certificate removes the warning, but it costs money each year.

## Phase 6: Collector health and alerts

Status: done on October 14, 2026. The alert is `backend/apps/collectors/alerts.py`, a worker task every 15 minutes.

Estimate: 0.5 day.

Changes from the first idea:

- The app reads the version from the User-Agent of each request, so it knows the version of older collectors too.
- The collector runs only on a race night. So "Salud" shows a collector that does not run as "apagado", which is normal. It is an error ("detenido en horario de carrera") only from 3 hours before to 3 hours after the start of a round.
- The alert goes to the users with the results permission, one time for each round, and only in a championship with an active collector.

1. "Colectores" shows for each collector: last contact, version, files in the queue, and the last error.
2. The collector sends a short status every 5 minutes.
3. On a race night, if a round passes its start time by 3 hours with no result file, the admins get a notification: "El colector no envió resultados".

## Order and total

| Phase | Estimate | Needs |
| --- | --- | --- |
| 0. Test the script idea | 0.5 day | A test server with CSP |
| 1. Publish clean imports | 1 day | Nothing |
| 2. Session sync and the script | 2.5 days | Phase 0 |
| 3. Conditions and disconnects | 1 day | Phase 2 for the session records |
| 4. Send the setup to the server | 2 days | Answers to open questions 1 and 2 |
| 5. Install with one click (server only) | 1 day | A GitHub Actions runner on Windows |
| 6. Health and alerts | 0.5 day | Phase 5 for the version field |
| Total | 8.5 days | |

Each phase is one pull request to `main`, with tests. The app stays usable after each phase.

## Open questions

1. Does the league run the server from a Content Manager preset, or from a plain server folder? Also, what is the public address and port of the server (phase 2)? A Content Manager preset keeps its own copy of the files. The collector must write to the files that the server reads.
2. Who stops and starts the AC server before a race? The plan expects an admin to do it by hand.
3. Does Real Penalty "Seconds penalty to final time" change `TotalTime` in the result file? Until we know, an admin applies this penalty.
4. Is the SmartScreen warning acceptable, or do we buy a code signing certificate? It now affects only the server PC.
5. Do all drivers use CSP? The `csp/` prefix in the result files says that the server needs it.
