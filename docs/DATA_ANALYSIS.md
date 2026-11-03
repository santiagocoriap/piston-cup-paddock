# Data analysis graphs

This file lists each requested graph and its state. The code is in `backend/apps/analytics/` and in `frontend/src/pages/analysis/`.

## Where the graphs are

- **Race and Lap:** the "Análisis" tab of a round page.
- **Season:** the "Análisis" section of a season page.
- **Driver:** the "Análisis de datos" section of a driver page.

## States

| State | Meaning |
|---|---|
| Built | The graph uses data that the app has. |
| Derived | The graph calculates its values from the lap times. The help text of the graph says how. |
| Elsewhere | Another tab of the app already shows it. |
| Model | The graph shows an estimate. The help text says that it is an estimate. |
| Needs data | The app does not collect the data. The graph is not built. |
| Not built | The data exists, but the graph is not built yet. |

## Data rules

- A clean lap has no invalid mark, no pit entry, no pit exit, and no incident. In a race, lap 1 is not clean.
- The order at the line comes from the sum of the lap times. A driver counts on a lap only after the driver completes it.
- The start position is the order of the best valid qualifying laps. It is not the real grid after penalties.
- A statistic of spread needs at least 3 clean laps.
- All formulas are in `backend/apps/analytics/metrics.py`.
- The season data stays in the cache for 10 minutes. A new result gives a new cache key.

## Race

| # | Graph | State | Note |
|---|---|---|---|
| 1 | Race position evolution | Derived | No overtake marks. |
| 2 | Gap to leader | Derived | |
| 3 | Driver-to-driver gap | Derived | |
| 4 | Positions gained and lost | Derived | DNF rows have a mark. |
| 5 | Classification progression | Derived | A slider, not an animation. |
| 6 | Lap time evolution | Built | |
| 7 | Pace distribution | Built | A box plot. |
| 8 | Average and median pace | Built | Median, mean, trimmed mean. |
| 9 | Consistency comparison | Built | Standard deviation and MAD. |
| 10 | Lap time heatmap | Built | |
| 11 | Pace trend | Built | Rolling median. |
| 12 | Performance delta | Built | In graph 8, in seconds and percent. |
| 13 | Overtaking leaderboard | Needs data | "Places gained at the line" is a replacement. It does not verify overtakes. |
| 14 | Battle timeline | Not built | The heatmap shows pits, incidents, and invalid laps by lap. |
| 15 | Time in traffic | Derived | Laps at the line, not time on the track. |
| 16 | First-lap performance | Derived | |
| 17 | Overtake and incident map | Elsewhere | The Incidents tab has the incident map. No overtakes. |
| 18 | Tyre strategy timeline | Built | Stops need a Real Penalty log. |
| 19 | Stint pace comparison | Needs data | Needs stints with different tyres. |
| 20 | Pit stop time | Needs data | |
| 21 | Tyre degradation | Needs data | |
| 22 | Undercut and overcut | Needs data | Needs a model too. |
| 23 | Fuel evolution | Needs data | |

## Lap

| # | Graph | State | Note |
|---|---|---|---|
| 1 | Lap time comparison | Built | The best lap of each driver. |
| 2 | Sector comparison | Built | A table of colors, not grouped bars. |
| 3 | Cumulative sector delta | Built | Bars with the running sum. |
| 4 | Theoretical best lap | Built | Bars, not stacked bars. |
| 5 | Sector consistency | Built | |
| 6 | Lap time improvement | Built | |
| 7 | Delta by distance | Elsewhere | Telemetry tab. |
| 8 | Speed trace | Elsewhere | Telemetry tab. |
| 9 | Throttle | Elsewhere | Telemetry tab. |
| 10 | Brake | Elsewhere | Telemetry tab. |
| 11 | Throttle and brake overlay | Elsewhere | Telemetry tab, on 2 lanes. |
| 12 | Gear | Elsewhere | Telemetry tab. |
| 13 | RPM | Elsewhere | Telemetry tab. |
| 14 | Steering | Elsewhere | Telemetry tab. |
| 15 | Acceleration and braking G | Needs data | The script does not send G values. |
| 16 | G-G diagram | Needs data | |
| 17 | Racing line comparison | Needs data | The script sends the place on the lap, not x and z. |
| 18 | Corner speed | Elsewhere | Engineer tab. |
| 19 | Braking point | Elsewhere | Engineer tab. |
| 20 | Corner time loss | Elsewhere | Telemetry tab map and Engineer tab. |
| 21 | Corner exit performance | Not built | |
| 22 | Steering smoothness | Not built | |
| 23 | Tyre temperature | Needs data | |
| 24 | Tyre pressure | Needs data | |
| 25 | Wheel slip | Needs data | |
| 26 | Suspension | Needs data | |
| 27 | Fuel per lap | Needs data | |
| 28 | Channel correlation | Not built | |

## Season

| # | Graph | State | Note |
|---|---|---|---|
| 1 | Points progression | Built | |
| 2 | Position evolution | Built | |
| 3 | Points per round | Built | In graph 5. |
| 4 | Gap evolution | Built | |
| 5 | Points contribution | Built | |
| 6 | Momentum | Built | Mean of 3 rounds. |
| 7 | Position change heatmap | Not built | Graph 2 shows the same data. |
| 8 | Finish position distribution | Built | |
| 9 | Qualifying heatmap | Derived | |
| 10 | Qualifying against race | Derived | |
| 11 | Positions gained | Derived | |
| 12 | Pace heatmap | Built | |
| 13 | Consistency ranking | Built | Lap deviation only. |
| 14 | Circuit performance | Not built | Graph 12 shows each round. No circuit metadata. |
| 15 | Field spread | Built | |
| 16 | Wins, podiums, poles | Built | Stacked bars, not grouped bars. |
| 17 | Milestone progression | Not built | |
| 18 | Records leaderboard | Elsewhere | Records page. |
| 19 | Finish frequency | Built | |
| 20 | Result calendar | Built | |
| 21 | Rivalry network | Needs data | |
| 22 | Title probability | Model | A value now, not an area over the season. Needs 3 rounds. |
| 23 | Scenario simulator | Not built | The title section shows the point scenarios. |
| 24 | Mathematical contention | Built | No tie-break, no bonus points. |
| 25 | Predicted standings | Model | Needs 3 rounds. |
| 26 | Performance forecast | Not built | |

## Driver

| # | Graph | State | Note |
|---|---|---|---|
| 1 | Performance radar | Built | Against one rival. |
| 2 | Performance evolution | Not built | Graphs 10 and 11 show the parts. |
| 3 | Pace against consistency | Built | |
| 4 | Driver form | Built | Finish position only. |
| 5 | Average finish | Built | In graph 4. |
| 6 | Personal best progression | Not built | Records page has the best laps. |
| 7 | Improvement by circuit | Not built | Needs repeated visits. |
| 8 | Performance by circuit type | Needs data | |
| 9 | Qualifying against race | Derived | Two lines, not connected dots. |
| 10 | Qualifying history | Derived | |
| 11 | Race pace history | Built | |
| 12 | Finish histogram | Built | |
| 13 | Positions gained | Derived | |
| 14 | Consistency across races | Not built | |
| 15 | Fastest lap against pace | Built | Bars, not a dumbbell. |
| 16 | Head-to-head results | Built | |
| 17 | Head-to-head qualifying | Derived | Wins only, no time gaps. |
| 18 | Head-to-head pace | Built | |
| 19 | Head-to-head points | Built | |
| 20 | Strengths comparison | Built | In graph 1. |
| 21 | Sector comparison | Not built | |
| 22 | Rivalry history | Not built | |
| 23 | Overtaking | Needs data | |
| 24 | Battle performance | Needs data | |
| 25 | Incident frequency | Not built | The data exists. |
| 26 | Finish reliability | Built | Stacked bar. |
| 27 | Result consistency | Elsewhere | Season graph 8. |
| 28 | Elo rating | Built | One season. No uncertainty band. |
| 29 | Expected against actual | Not built | |
| 30 | Performance decomposition | Not built | The radar shows the parts. |
| 31 | Development forecast | Needs data | Needs more rounds. |
| 32 | Driver similarity | Not built | |

## Shared tools

| Tool | State |
|---|---|
| Driver filter | Built: one filter for each page. It applies to all graphs. |
| Hover values | Built on line graphs. Other graphs use the browser tooltip. |
| Zoom | Built on line graphs: drag, then a double click to reset. |
| Full screen | Built. |
| SVG export | Built. |
| CSV export | Built on most graphs, not on all. |
| PNG export | Not built. |
| Shared crosshair between graphs | Not built. |
| Filters by circuit, tyre, or weather | Not built. |
