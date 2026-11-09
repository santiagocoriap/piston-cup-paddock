"""The data of the analysis pages, from the applied result files and the current results.

docs/DATA_ANALYSIS.md lists each graph and the data that it uses.
"""

import json
from dataclasses import dataclass, field

from django.core.cache import cache
from django.db.models import Max

from apps.catalog.track_line import circuit_type
from apps.competition.models import Round, Season, Session
from apps.imports.lap_analysis import _exclusion
from apps.imports.lap_services import RoundLaps, round_laps
from apps.results.models import RaceResult
from apps.results.services import current_lines, season_standings
from apps.telemetry.services import access

from . import metrics
from .racecraft import round_racecraft

CACHE_SECONDS = 600
# The prediction needs this many rounds of results.
PREDICT_ROUNDS = 3


@dataclass
class LapPoint:
    number: int
    ms: int
    sectors_ms: list[int]
    valid: bool
    clean: bool
    pit: str | None
    contact: bool
    tyre: str
    # Only for a race: the order at the line, from the sum of the lap times.
    position: int | None = None
    gap_to_leader_ms: int | None = None
    ahead_ms: int | None = None
    # From the telemetry, when the viewer can see the telemetry of the driver.
    fuel_used: float | None = None
    fuel_left: float | None = None
    pit_ms: int | None = None
    wear: float | None = None


@dataclass
class Stint:
    start_lap: int
    end_lap: int
    tyre: str
    laps: int
    median_ms: float | None
    # The change of the clean lap time for each lap. None with too few clean laps. An estimate.
    trend_ms: float | None
    # The time that the stop at the end of the stint cost: the in-lap and the out-lap against 2
    # normal laps. None without a stop.
    pit_loss_ms: int | None = None


@dataclass
class RoundDriver:
    entry_id: int
    driver_id: int
    name: str
    number: int
    grid: int | None
    finish: int | None
    status: str | None
    points: int | None
    best_ms: int | None
    best_lap: int | None
    theoretical_ms: int | None
    best_sectors_ms: list[int | None]
    spread: metrics.Spread
    battle: dict[str, int] | None
    laps: list[LapPoint]
    stints: list[Stint] = field(default_factory=list)
    overtakes: int | None = None
    overtaken: int | None = None
    attacks: int | None = None
    attacks_won: int | None = None
    defenses: int | None = None
    defenses_won: int | None = None
    battle_seconds: int | None = None


@dataclass
class OvertakeEvent:
    at_s: int
    lap: int
    attacker_id: int
    defender_id: int
    x: float | None
    z: float | None


@dataclass
class RoundAnalysis:
    session: str
    sessions: list[str]
    has_sectors: bool
    has_pit_data: bool
    clean_rules: list[str]
    drivers: list[RoundDriver]
    has_positions: bool = False
    overtakes: list[OvertakeEvent] = field(default_factory=list)


def _stints(rows, rules: list[str]) -> list[Stint]:
    """A stint ends with a pit entry, or when the tyre changes."""
    groups: list[list] = []
    for row in rows:
        if groups and groups[-1][-1].pit != "in" and groups[-1][-1].tyre == row.tyre:
            groups[-1].append(row)
        else:
            groups.append([row])
    stints = []
    for index, group in enumerate(groups):
        clean = [r for r in group if not _exclusion(r, rules)]
        median = metrics.spread([r.time_ms for r in clean]).median
        fit = metrics.trend([(r.lap_number, r.time_ms) for r in clean])
        loss = None
        if group[-1].pit == "in" and index + 1 < len(groups) and median:
            out_lap = groups[index + 1][0].time_ms
            loss = round(group[-1].time_ms + out_lap - 2 * median)
        stints.append(
            Stint(
                start_lap=group[0].lap_number,
                end_lap=group[-1].lap_number,
                tyre=group[0].tyre,
                laps=len(group),
                median_ms=median,
                trend_ms=round(fit[0], 1) if fit else None,
                pit_loss_ms=loss,
            )
        )
    return stints


def _add_racecraft(round_: Round, analysis: RoundAnalysis) -> None:
    has, found, cars = round_racecraft(round_)
    analysis.has_positions = has
    if not has:
        return
    drivers = {d.entry_id: d for d in analysis.drivers}
    entry = {car: e.id for car, e in cars.items()}
    driver_of = {car: e.driver_id for car, e in cars.items()}
    for driver in drivers.values():
        driver.overtakes = driver.overtaken = driver.battle_seconds = 0
        driver.attacks = driver.attacks_won = driver.defenses = driver.defenses_won = 0
    for overtake in found.overtakes:
        analysis.overtakes.append(
            OvertakeEvent(
                overtake.at_s,
                overtake.lap,
                driver_of[overtake.attacker],
                driver_of[overtake.defender],
                overtake.x,
                overtake.z,
            )
        )
        if attacker := drivers.get(entry[overtake.attacker]):
            attacker.overtakes += 1
        if defender := drivers.get(entry[overtake.defender]):
            defender.overtaken += 1
    for battle in found.battles:
        behind, ahead = drivers.get(entry[battle.a]), drivers.get(entry[battle.b])
        if behind:
            behind.attacks += 1
            behind.attacks_won += battle.passed
            behind.battle_seconds += battle.seconds
        if ahead:
            ahead.defenses += 1
            ahead.defenses_won += not battle.passed
            ahead.battle_seconds += battle.seconds


def add_telemetry(analysis: RoundAnalysis, round_: Round, viewer) -> None:
    """The fuel, pit time, and tyre wear of each lap. Each driver chooses who sees the telemetry,
    so a lap of another driver gets these values only with full access."""
    drivers = {d.driver_id: d for d in analysis.drivers}
    laps = round_.telemetry_laps.filter(session_type=analysis.session).select_related(
        "driver", "round__season__championship"
    )
    levels: dict[int, str | None] = {}
    for lap in laps:
        driver = drivers.get(lap.driver_id)
        if driver is None or not lap.summary:
            continue
        if lap.driver_id not in levels:
            levels[lap.driver_id] = access(viewer, lap)
        if levels[lap.driver_id] != "full":
            continue
        point = next((p for p in driver.laps if p.number == lap.lap_number), None)
        if point:
            point.fuel_used = lap.summary.get("fuel_used")
            point.fuel_left = lap.summary.get("fuel_end")
            point.pit_ms = lap.summary.get("pit_ms")
            point.wear = lap.summary.get("wear")


def _grid(round_: Round) -> dict[int, int]:
    """The start position of each entry: the order of the best valid laps in qualifying."""
    laps = round_laps(round_, Session.Kind.QUALIFYING)
    timed = [(d.best_lap_ms, info.entry_id) for info, d in laps.drivers if d.best_lap_ms]
    return {entry_id: index + 1 for index, (_, entry_id) in enumerate(sorted(timed))}


def round_analysis(round_: Round, kind: str) -> RoundAnalysis:
    data: RoundLaps = round_laps(round_, kind)
    race = kind == Session.Kind.RACE
    grid = _grid(round_) if race else {}
    lines = (
        {row.entry_id: row for row in current_lines(version__result__round=round_)} if race else {}
    )
    ordered = {
        info.entry_id: [m.row.time_ms for m in sorted(d.laps, key=lambda m: m.row.lap_number)]
        for info, d in data.drivers
    }
    orders = metrics.lap_order(ordered) if race else {}
    entries = {e.id: e for e in round_.season.entries.all()}
    drivers = []
    for info, laps in data.drivers:
        rows = sorted((m.row for m in laps.laps), key=lambda r: r.lap_number)
        clean = [r.time_ms for r in rows if not _exclusion(r, data.clean_rules)]
        order = orders.get(info.entry_id, [])
        points = []
        for index, row in enumerate(rows):
            at_line = order[index] if index < len(order) else None
            points.append(
                LapPoint(
                    number=row.lap_number,
                    ms=row.time_ms,
                    sectors_ms=row.sectors_ms,
                    valid=row.valid,
                    clean=not _exclusion(row, data.clean_rules),
                    pit=row.pit,
                    contact=row.contact,
                    tyre=row.tyre,
                    position=at_line.position if at_line else None,
                    gap_to_leader_ms=at_line.gap_to_leader_ms if at_line else None,
                    ahead_ms=at_line.ahead_ms if at_line else None,
                )
            )
        line = lines.get(info.entry_id)
        drivers.append(
            RoundDriver(
                entry_id=info.entry_id,
                driver_id=entries[info.entry_id].driver_id,
                name=info.driver_name,
                number=info.number,
                grid=grid.get(info.entry_id),
                finish=line.position if line else None,
                status=line.status if line else None,
                points=line.points if line else None,
                best_ms=laps.best_lap_ms,
                best_lap=laps.best_lap_number,
                theoretical_ms=laps.theoretical_ms,
                best_sectors_ms=laps.best_sectors_ms,
                spread=metrics.spread(clean),
                battle=metrics.battle_share(order) if race else None,
                laps=points,
                stints=_stints(rows, data.clean_rules) if race else [],
            )
        )
    analysis = RoundAnalysis(
        data.session, data.sessions, data.has_sectors, data.has_pit_data, data.clean_rules, drivers
    )
    if race:
        _add_racecraft(round_, analysis)
    return analysis


@dataclass
class RoundCell:
    """One driver in one round of a season. None: no value, for example no laps."""

    round_id: int
    number: int
    track: str
    grid: int | None = None
    finish: int | None = None
    status: str | None = None
    points: int = 0
    total_points: int = 0
    rank: int | None = None
    gap_to_leader: int | None = None
    pole: bool = False
    fastest_lap: bool = False
    best_ms: int | None = None
    median_ms: float | None = None
    stdev_ms: float | None = None
    # The median clean lap against the best median of the round, in percent. 0 is the best.
    pace_pct: float | None = None
    # The best qualifying lap against the pole lap, in percent. 0 is the pole.
    qualifying_pct: float | None = None
    elo: float | None = None
    overtakes: int | None = None
    attacks: int | None = None
    attacks_won: int | None = None
    defenses: int | None = None
    defenses_won: int | None = None
    # The incident laps of the driver in the race, from the server collector.
    incidents: int | None = None
    sectors_ms: list[int | None] = field(default_factory=list)


@dataclass
class SeasonDriver:
    entry_id: int
    driver_id: int
    name: str
    number: int
    rank: int
    points: int
    wins: int
    podiums: int
    poles: int
    fastest_laps: int
    finishes: int
    dnfs: int
    cells: list[RoundCell]
    # A score from 0 to 100 inside the field for each part of the radar. See _radar.
    scores: dict[str, int | None] = field(default_factory=dict)
    # The mean values under the scores. None without enough data.
    average_pace_pct: float | None = None
    average_stdev_ms: float | None = None
    max_points: int | None = None
    can_win: bool | None = None
    # A Monte Carlo estimate. None with too few rounds. See metrics.predict.
    win_pct: float | None = None
    expected_rank: float | None = None
    rank_odds: list[float] | None = None
    # The trend of pace_pct and the next rounds. An estimate. None with too few rounds.
    pace_trend: float | None = None
    pace_forecast: list["ForecastPoint"] = field(default_factory=list)


@dataclass
class ForecastPoint:
    number: int
    value: float
    low: float
    high: float


@dataclass
class Rivalry:
    a: int  # Driver IDs.
    b: int
    battles: int
    seconds: int
    passes: int


@dataclass
class SeasonRound:
    id: int
    number: int
    track: str
    has_result: bool
    # From the game file of the layout: "high_speed", "mixed", or "technical". None without it.
    circuit_type: str | None = None
    corners: int | None = None
    # The best median clean lap against the last one, in percent: the spread of the field.
    field_spread_pct: float | None = None


@dataclass
class SeasonAnalysis:
    season_id: int
    season_name: str
    championship_name: str
    planned_rounds: int
    remaining_rounds: int
    points_by_position: list[int]
    rounds: list[SeasonRound]
    drivers: list[SeasonDriver]
    rivalries: list[Rivalry] = field(default_factory=list)


def _layout_type(round_: Round) -> tuple[str | None, int | None]:
    line = round_.track_layout.line
    if not line:
        return None, None
    try:
        with line.open("rb") as handle:
            return circuit_type(json.loads(handle.read()))
    except (OSError, ValueError, KeyError):
        return None, None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _radar(drivers: list[SeasonDriver]) -> None:
    """Each part is a score from 0 to 100 against the other drivers of the season:
    pace (mean pace_pct), consistency (mean lap deviation), qualifying (mean start position),
    results (mean points), racecraft (mean places gained), reliability (share of finishes)."""
    keys = [d.entry_id for d in drivers]

    def of(values: list[float | None]) -> dict[object, float | None]:
        return dict(zip(keys, values, strict=True))

    def raced(driver: SeasonDriver) -> list[RoundCell]:
        return [c for c in driver.cells if c.status is not None]

    parts = {
        "pace": metrics.scale(
            of([_mean([c.pace_pct for c in d.cells if c.pace_pct is not None]) for d in drivers]),
            lower_is_better=True,
        ),
        "consistency": metrics.scale(
            of([_mean([c.stdev_ms for c in d.cells if c.stdev_ms is not None]) for d in drivers]),
            lower_is_better=True,
        ),
        "qualifying": metrics.scale(
            of([_mean([c.grid for c in d.cells if c.grid is not None]) for d in drivers]),
            lower_is_better=True,
        ),
        "results": metrics.scale(
            of([_mean([c.points for c in raced(d)]) for d in drivers]), lower_is_better=False
        ),
        "racecraft": metrics.scale(
            of(
                [
                    _mean([c.grid - c.finish for c in d.cells if c.grid and c.finish])
                    for d in drivers
                ]
            ),
            lower_is_better=False,
        ),
        "reliability": metrics.scale(
            of([d.finishes / len(raced(d)) if raced(d) else None for d in drivers]),
            lower_is_better=False,
        ),
    }
    for driver in drivers:
        driver.scores = {name: part[driver.entry_id] for name, part in parts.items()}
        driver.average_pace_pct = _mean(
            [c.pace_pct for c in driver.cells if c.pace_pct is not None]
        )
        driver.average_stdev_ms = _mean(
            [c.stdev_ms for c in driver.cells if c.stdev_ms is not None]
        )


def _build_season(season: Season) -> SeasonAnalysis:
    entries = {e.id: e for e in season.entries.select_related("driver")}
    rounds = list(
        season.rounds.filter(cancelled_at__isnull=True)
        .select_related("track_layout__track")
        .order_by("number")
    )
    lines: dict[tuple[int, int], object] = {}
    for row in current_lines(version__result__round__season=season).select_related(
        "version__result"
    ):
        lines[(row.version.result.round_id, row.entry_id)] = row

    cells: dict[int, list[RoundCell]] = {entry_id: [] for entry_id in entries}
    season_rounds = []
    elo_races = []
    rivalries: dict[tuple[int, int], Rivalry] = {}
    for round_ in rounds:
        analysis = round_analysis(round_, Session.Kind.RACE)
        qualifying = round_laps(round_, Session.Kind.QUALIFYING)
        best_qualifying = {
            i.entry_id: d.best_lap_ms for i, d in qualifying.drivers if d.best_lap_ms
        }
        pole = min(best_qualifying.values(), default=None)
        by_entry = {d.entry_id: d for d in analysis.drivers}
        medians = [d.spread.median for d in analysis.drivers if d.spread.median]
        best_median = min(medians, default=None)
        # The league gives no bonus for these, so the result lines do not mark them: the laps do.
        fastest = min((d.best_ms for d in analysis.drivers if d.best_ms), default=None)
        track = round_.track_layout.track.name
        finished = []
        for entry_id in entries:
            line = lines.get((round_.id, entry_id))
            driver = by_entry.get(entry_id)
            median = driver.spread.median if driver else None
            cell = RoundCell(
                round_id=round_.id,
                number=round_.number,
                track=track,
                grid=driver.grid if driver else None,
                finish=line.position if line else None,
                status=line.status if line else None,
                points=line.points if line else 0,
                pole=bool(line and line.pole)
                or (pole is not None and best_qualifying.get(entry_id) == pole),
                fastest_lap=bool(line and line.fastest_lap)
                or (fastest is not None and driver is not None and driver.best_ms == fastest),
                best_ms=driver.best_ms if driver else None,
                median_ms=median,
                stdev_ms=driver.spread.stdev if driver else None,
                pace_pct=round((median / best_median - 1) * 100, 3)
                if median and best_median
                else None,
                qualifying_pct=round((best_qualifying[entry_id] / pole - 1) * 100, 3)
                if entry_id in best_qualifying and pole
                else None,
                overtakes=driver.overtakes if driver else None,
                attacks=driver.attacks if driver else None,
                attacks_won=driver.attacks_won if driver else None,
                defenses=driver.defenses if driver else None,
                defenses_won=driver.defenses_won if driver else None,
                incidents=sum(1 for lap in driver.laps if lap.contact) if driver else None,
                sectors_ms=driver.best_sectors_ms if driver else [],
            )
            cells[entry_id].append(cell)
            if line and line.position:
                finished.append((entry_id, line.position))
        elo_races.append(finished)
        kind, corners = _layout_type(round_)
        _, found, cars = round_racecraft(round_)  # The cache has it from round_analysis.
        for battle in found.battles:
            if battle.a not in cars or battle.b not in cars:
                continue
            pair = tuple(sorted((cars[battle.a].driver_id, cars[battle.b].driver_id)))
            seen = rivalries.setdefault(pair, Rivalry(pair[0], pair[1], 0, 0, 0))
            seen.battles += 1
            seen.seconds += battle.seconds
            seen.passes += battle.passed
        season_rounds.append(
            SeasonRound(
                id=round_.id,
                number=round_.number,
                track=track,
                has_result=any((round_.id, e) in lines for e in entries),
                circuit_type=kind,
                corners=corners,
                field_spread_pct=round((max(medians) / best_median - 1) * 100, 3)
                if len(medians) > 1
                else None,
            )
        )

    # The points and the rank after each round.
    for index, round_ in enumerate(rounds):
        table = season_standings(season, up_to_round=round_.number)
        leader = table[0].points if table else 0
        for row in table:
            cell = cells[row.entry_id][index]
            cell.total_points = row.points
            cell.rank = row.rank
            cell.gap_to_leader = leader - row.points

    ratings = metrics.elo(elo_races)
    for entry_id, history in ratings.items():
        values = iter(history)
        for cell, race in zip(cells[entry_id], elo_races, strict=True):
            if len(race) > 1 and any(key == entry_id for key, _ in race):
                cell.elo = next(values)

    drivers = []
    for row in season_standings(season):
        entry = entries[row.entry_id]
        mine = cells[row.entry_id]
        drivers.append(
            SeasonDriver(
                entry_id=row.entry_id,
                driver_id=entry.driver_id,
                name=entry.driver.display_name,
                number=entry.number,
                rank=row.rank,
                points=row.points,
                wins=row.wins,
                podiums=sum(1 for c in mine if c.finish and c.finish <= 3),
                poles=sum(1 for c in mine if c.pole),
                fastest_laps=sum(1 for c in mine if c.fastest_lap),
                finishes=sum(1 for c in mine if c.status == "finished"),
                dnfs=sum(1 for c in mine if c.status == "dnf"),
                cells=mine,
            )
        )
    _radar(drivers)

    rules = _points_table(season)
    remaining = max(season.planned_round_count - sum(r.has_result for r in season_rounds), 0)
    per_round = max(rules, default=0)
    leader_points = drivers[0].points if drivers else 0
    for driver in drivers:
        driver.max_points = driver.points + remaining * per_round
        driver.can_win = driver.max_points >= leader_points
    done = {r.number for r in season_rounds if r.has_result}
    if len(done) >= PREDICT_ROUNDS and remaining > 0:
        odds = metrics.predict(
            {d.entry_id: d.points for d in drivers},
            {
                d.entry_id: [c.points for c in d.cells if c.number in done and c.status]
                for d in drivers
            },
            remaining,
            seed=season.id,
        )
        for driver in drivers:
            found = odds[driver.entry_id]
            driver.win_pct = found.win_pct
            driver.expected_rank = found.expected_rank
            driver.rank_odds = found.rank_odds
    for driver in drivers:
        known = [(c.number, c.pace_pct) for c in driver.cells if c.pace_pct is not None]
        fit = metrics.trend(known)
        if fit:
            slope, start, error = fit
            driver.pace_trend = round(slope, 4)
            driver.pace_forecast = [
                ForecastPoint(
                    number=r.number,
                    value=round(start + slope * r.number, 3),
                    low=round(start + slope * r.number - 2 * error, 3),
                    high=round(start + slope * r.number + 2 * error, 3),
                )
                for r in season_rounds
                if not r.has_result
            ]
    return SeasonAnalysis(
        season_id=season.id,
        season_name=season.name,
        championship_name=season.championship.name,
        planned_rounds=season.planned_round_count,
        remaining_rounds=remaining,
        points_by_position=rules,
        rounds=season_rounds,
        drivers=drivers,
        rivalries=sorted(rivalries.values(), key=lambda r: -r.seconds),
    )


def _points_table(season: Season) -> list[int]:
    current = season.rules_versions.order_by("-number").first()
    return list(current.points_by_position) if current else []


def season_analysis(season: Season) -> SeasonAnalysis:
    """The result of a season reads every file of the season, so the app keeps it for a while.
    A new result or a new file gives a new cache key."""
    changed = RaceResult.objects.filter(round__season=season).aggregate(at=Max("updated_at"))["at"]
    key = f"season-analysis:{season.id}:{changed.isoformat() if changed else 'none'}"
    cached = cache.get(key)
    if cached is None:
        cached = _build_season(season)
        cache.set(key, cached, CACHE_SECONDS)
    return cached
