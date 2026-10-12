# Data sources

Date: October 11, 2026

Status: Based on the samples in `samples/2026-10-11-ks-highlands/`. Ticket #4 records this map.

This document shows which data each source gives, and the gaps. A ticket must not promise a field that this map marks as not available.

## Sources

| Source | Where it comes from | When it exists |
| --- | --- | --- |
| AC result file | `server/results/YYYY_M_D_H_M_TYPE.json` | One file when a session ends. The name shows the end time, not the start time |
| Real Penalty log | `server/realpenalty/logs/<type>_penalty_YYYYMMDD_HHMMSS.log` | One file for each session start, also for a start that stops |
| UDP plugin data | A plugin such as `current-scripts/live_logger.py` | Only when the plugin runs during the session |
| Manual input | An admin types the value in the app | Always |

## Field map for the first release

| Field | Source | Notes |
| --- | --- | --- |
| Track and layout | Result file: `TrackName`, `TrackConfig` | Remove the CSP prefix: `csp/3460/../D/../ks_highlands` gives `ks_highlands` |
| Session type | Result file: `Type`. Real Penalty log: `Type: 1/2/3` | 1 is practice, 2 is qualifying, 3 is race |
| Session length | Real Penalty log: `Time:` in minutes, `Laps:` | The result file shows `DurationSecs: 0` for a timed race. Do not use it |
| Session end time | Result file name | Local time of the server |
| Session start time | Real Penalty log name and first line | Not in the result file |
| Entry list | Result file: `Cars[]` | Contains reserved slots for drivers who did not join, one empty slot, and a `Race Control` slot |
| Driver identity | Result file: `Laps[].DriverGuid` | Use the GUID of the laps, not of `Result[]`. See "GUID stability" |
| Car model and skin | Result file: `Cars[].Model`, `Skin` | The Real Penalty log writes the model name in lower case |
| Classification order | Result file: order of `Result[]` | Sorted by laps, then by total time |
| Total time | Result file: `Result[].TotalTime` in ms | 0 when the driver did no lap |
| Laps completed | Count of `Laps[]` for the car | Not a field. The app counts the laps |
| Best lap | Result file: `Result[].BestLap` in ms | `999999999` means no lap |
| Lap times | Result file: `Laps[].LapTime` in ms | |
| Sectors | Result file: `Laps[].Sectors[]` in ms | 3 sectors on this track |
| Tyre compound | Result file: `Laps[].Tyre` | Letters such as `S`, `M`, `H` |
| Lap time stamp | Result file: `Laps[].Timestamp` | Milliseconds since the server started, not a clock time |
| Observed ballast and restrictor | Result file: `Cars[]`, `Result[]`, `Laps[]` | The values that the server used. Compare with the assigned values |
| Lap validity (cuts) | Real Penalty log: `Cutting`, `Cutting Warning`, `Invalid Qualify Lap` | `Laps[].Cuts` is 0 in all samples. Real Penalty records the cuts instead |
| Collisions | Result file: `Events[]` with `COLLISION_WITH_CAR` and `COLLISION_WITH_ENV` | Has car, other car, impact speed, and position. Has no time and no lap |
| Penalties | Real Penalty log: `New penalty`, `Penalty Taken`, `Penalty wrong taken`, `Seconds penalty to final time`, DSQ summary | The result file has no penalty field |
| Pit stops and tyre change | Real Penalty log: `Pit lane entered`, `Pit lane left` with tyres, `Car refuelled` | |
| Race finish status (DNF) | Manual input | No field shows a DNF. A car with fewer laps can be a lapped car or a DNF |
| DNS | Result file | An entry with no laps did not start |
| DSQ | Real Penalty DSQ summary, or manual input | |
| Conditions (weather, temperature, grip) | Manual input | Not in the result file or the Real Penalty log |

## How events look in the data

**A restart of a race.** Real Penalty writes a new race log with a new header. The AC server writes no result file for the stopped start. On this night, 21 race logs exist and only one result file exists. The app must find a restart from the Real Penalty logs, or an admin enters it.

**A new session.** Real Penalty writes a new log with a different `Type`. The AC server writes a result file for the session that ended.

**A reconnect.** No result file and no Real Penalty log records a connection or a disconnection. Only the UDP plugin receives these events.

## GUID stability

- In each file, each car has one GUID in its laps.
- The same GUID stays on the same car in practice, qualifying, and race.
- In the race file, car 3 has one GUID in `Cars[]` and `Result[]`, and a different GUID in `Laps[]`. The display name is the same. The import must match drivers by the GUID of the laps and show a warning when the GUIDs are not the same.

## Open questions

1. Does `Seconds penalty to final time` from Real Penalty change `TotalTime` in the result file? The samples have this penalty only in a stopped start, so they do not answer this. The app must not apply a time penalty twice (ticket #20).
2. What is the Real Penalty version on the race server?
3. Which data does the UDP plugin give for a stopped start? It is the only source with a time for each collision. The rule "the driver who crashes first causes the restart" needs that time.

## Fallbacks for the first release

Each first-release field has a source above or a manual fallback:

- An admin enters the restarts, the restart responsibility, the DNF status, and the conditions.
- An admin confirms the classification after the import preview.
- The import uses the result file. The Real Penalty log import comes later (ticket #20).
