# Race samples

These files are real league data with fake values for driver names, Steam GUIDs, team names, and the server name. The fake GUIDs are below the range of real Steam accounts.

The raw files stay in `samples-raw/`. Git ignores that folder. Do not commit raw files.

## 2026-10-11-ks-highlands

One race night at `ks_highlands`, layout `layout_long`, with 12 cars.

| File | Source | Contents |
| --- | --- | --- |
| `2026_10_11_18_38_PRACTICE.json` | AC server results | Practice laps and collision events |
| `2026_10_11_18_54_QUALIFY.json` | AC server results | Qualifying laps and collision events |
| `2026_10_11_20_7_RACE.json` | AC server results | The completed race: classification, laps, sectors, tyres, ballast, restrictor, and collisions |
| `realpenalty/*.log` | Real Penalty server plugin | One log for each session start: pit stops, refuelling, cuts, teleports, penalties |

## Findings

- The night has 21 race starts in the Real Penalty logs. 20 starts stopped in less than 4 minutes. Only the last start finished.
- The AC server wrote a result file only for the finished race. The 20 abandoned starts have no result file. Only the Real Penalty logs show them.
- The Real Penalty logs do not record collisions. The collisions of an abandoned start need the UDP plugin data from `current-scripts/live_logger.py`.
- The result files contain the ballast and the restrictor of each car. The app can compare them with the assigned values.
- The track name has a CSP prefix: `csp/3460/../D/../ks_highlands`. The app must remove the prefix to get `ks_highlands`.
