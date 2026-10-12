# League rules

Date: October 11, 2026

Status: Adopted for the first release. Ticket #2 records these decisions.

These rules are the default rules version for a new season. An admin can change them for one season. The app must calculate with these values and must not invent other values.

## Points

| Position | Points |
| --- | --- |
| 1 | 25 |
| 2 | 18 |
| 3 | 15 |
| 4 | 12 |
| 5 | 10 |
| 6 | 8 |
| 7 | 6 |
| 8 | 4 |
| 9 | 2 |
| 10 | 1 |
| 11 and lower | 0 |

- There is no bonus for pole position or for the fastest lap.
- Only race sessions give points. Practice and qualifying give no points.

## Classification

- There is no minimum distance. Each driver who starts the race is classified, also after a DNF.
- A DNF driver gets the points for their classified position.
- A DNS driver gets 0 points.
- A DSQ driver gets the points for the last classified position of that race.

## Season tiebreaker

If two or more drivers have equal points, the app compares their results in this order:

1. The number of wins.
2. The number of 2nd places.
3. The number of 3rd places, and so on for each lower position.

If all counts are equal, the drivers share the position.

## Ballast and restrictor

Only a race win adds ballast and restrictor. The step depends on the number of race wins of the driver in the current season.

| Season win | Ballast added | Restrictor added |
| --- | --- | --- |
| 1st | +10 kg | +2 % |
| 2nd | +10 kg | +2 % |
| 3rd | +5 kg | +1 % |
| 4th and later | +3 kg | +1 % |

- The maximum is 45 kg and 5 %.
- The values add up. Each new value applies from the next round.
- A finish of 2nd or lower removes 3 kg and 1 %. A DNF and a DSQ count as a finish of 2nd or lower. The values never go below 0.
- A removal does not change the win count. Example: 3 wins give 25 kg. A 2nd place gives 22 kg. The next win is the 4th season win and adds 3 kg, so the value is 25 kg.
- A driver who does not start a round (DNS or absent) keeps the same values.
- All values and win counts go back to 0 at the start of each season.

Examples for a driver who only wins:

| Season wins | Ballast | Restrictor |
| --- | --- | --- |
| 1 | 10 kg | 2 % |
| 2 | 20 kg | 4 % |
| 3 | 25 kg | 5 % |
| 4 | 28 kg | 5 % |
| 8 | 40 kg | 5 % |
| 9 | 43 kg | 5 % |
| 10 | 45 kg | 5 % |

## Official results and protests

- The app publishes provisional results first.
- An admin approves the results to make them official.
- Drivers have 1 hour to send a protest after the provisional results appear. An admin can change this time for a season.

## Restarts

- Only restarts of a race session count. Restarts in practice or qualifying do not count.
- The driver who crashes first in the abandoned start causes the restart.
- An admin confirms the responsible driver. The app can suggest the driver from the first collision in the data, but it does not confirm the driver.
- A restart for a server or technical problem has no responsible driver.

## Track records

- Qualifying records and race records are separate boards.
- A race record comes only from the accepted race start, after the results are official.
- Laps from abandoned starts do not become records.
