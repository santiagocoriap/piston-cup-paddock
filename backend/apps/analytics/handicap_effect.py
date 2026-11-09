"""How much time the ballast and the restrictor cost: an estimate from a model, and a check
against the lap times of the season.

The model: lap time grows with the weight and falls with the power. From sim racing data, a
lap is about MASS_EXPONENT slower for each part of extra weight, and POWER_EXPONENT slower for
each part of less power:

    lap factor = (mass with ballast / mass) ** MASS_EXPONENT
               * (power / power with restrictor) ** POWER_EXPONENT

The mass is the car weight of the game data plus DRIVER_KG. In AC, a restrictor of N % takes
about N % of the power at high rpm, so the model uses N % less power. It is an estimate: the
real cost depends on the track (a track with long straights loses more with a restrictor).

The check: for each driver, the median clean lap against the best median of the round
(pace_pct). The rounds with ballast or restrictor against the rounds with none give the
measured cost. With few rounds, this number has a large error.
"""

from dataclasses import dataclass, field
from statistics import median

from apps.competition.models import Season
from apps.handicaps.services import assigned_values
from apps.results.services import current_lines

from .services import season_analysis

MASS_EXPONENT = 0.15
POWER_EXPONENT = 0.30
DRIVER_KG = 75


def lap_factor(weight_kg: float, ballast_kg: float, restrictor_pct: float) -> float:
    """The lap time with the handicap divided by the lap time with none."""
    mass = weight_kg + DRIVER_KG
    power_left = max(1 - restrictor_pct / 100, 0.01)
    return ((mass + ballast_kg) / mass) ** MASS_EXPONENT * (1 / power_left) ** POWER_EXPONENT


@dataclass
class HandicapRound:
    number: int
    ballast_kg: int
    restrictor_pct: int
    laps: int | None
    lap_ms: float | None  # The median clean lap of the driver.
    model_ms: float | None  # The model cost on each lap.
    pace_pct: float | None


@dataclass
class HandicapDriver:
    entry_id: int
    driver_id: int
    name: str
    car: str
    rounds: list[HandicapRound] = field(default_factory=list)
    model_total_ms: float | None = None  # The model cost on all race laps of the season.
    model_pct: float | None = None  # The mean model cost of the rounds with a handicap.
    measured_pct: float | None = None  # Handicap rounds minus free rounds, in pace_pct.


@dataclass
class HandicapCar:
    car_id: int
    name: str
    weight_kg: int | None
    power_hp: int | None
    lap_ms: float | None  # The median clean lap of the season with this car.
    per_10kg_ms: float | None
    per_1pct_ms: float | None


@dataclass
class HandicapEffect:
    mass_exponent: float
    power_exponent: float
    driver_kg: int
    cars: list[HandicapCar]
    drivers: list[HandicapDriver]
    # All drivers together: the mean model cost and the mean measured cost, in percent.
    model_pct: float | None
    measured_pct: float | None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def handicap_effect(season: Season) -> HandicapEffect:
    analysis = season_analysis(season)
    entries = {e.id: e for e in season.entries.select_related("driver", "car")}
    done = [r for r in analysis.rounds if r.has_result]
    rounds = {r.id: r for r in season.rounds.filter(id__in=[r.id for r in done])}
    values = {round_id: assigned_values(round_) for round_id, round_ in rounds.items()}
    laps = {(line.version.result.round_id, line.entry_id): line.laps for line in _lines(season)}
    drivers = []
    car_laps: dict[int, list[float]] = {}
    for driver in analysis.drivers:
        entry = entries.get(driver.entry_id)
        car = entry.car if entry else None
        row = HandicapDriver(
            driver.entry_id, driver.driver_id, driver.name, car.name if car else ""
        )
        for cell in driver.cells:
            if cell.round_id not in rounds:
                continue
            kg, pct = values[cell.round_id].get(driver.entry_id, (0, 0))
            model = None
            if car and car.weight_kg and cell.median_ms:
                model = round(cell.median_ms * (lap_factor(car.weight_kg, kg, pct) - 1), 1)
            if car and cell.median_ms:
                car_laps.setdefault(car.id, []).append(cell.median_ms)
            row.rounds.append(
                HandicapRound(
                    cell.number,
                    kg,
                    pct,
                    laps.get((cell.round_id, driver.entry_id)),
                    cell.median_ms,
                    model,
                    cell.pace_pct,
                )
            )
        costed = [r for r in row.rounds if r.model_ms is not None and r.laps]
        if costed:
            row.model_total_ms = round(sum(r.model_ms * r.laps for r in costed), 1)
        loaded = [r for r in row.rounds if r.ballast_kg or r.restrictor_pct]
        free = [r for r in row.rounds if not (r.ballast_kg or r.restrictor_pct)]
        row.model_pct = _mean(
            [r.model_ms / r.lap_ms * 100 for r in loaded if r.model_ms is not None and r.lap_ms]
        )
        loaded_pace = [r.pace_pct for r in loaded if r.pace_pct is not None]
        free_pace = [r.pace_pct for r in free if r.pace_pct is not None]
        if loaded_pace and free_pace:
            row.measured_pct = round(_mean(loaded_pace) - _mean(free_pace), 3)
        drivers.append(row)

    cars = []
    for car in {e.car.id: e.car for e in entries.values() if e.car}.values():
        lap = median(car_laps[car.id]) if car.id in car_laps else None
        known = lap is not None and car.weight_kg
        cars.append(
            HandicapCar(
                car.id,
                car.name,
                car.weight_kg,
                car.power_hp,
                lap,
                round(lap * (lap_factor(car.weight_kg, 10, 0) - 1), 1) if known else None,
                round(lap * (lap_factor(car.weight_kg, 0, 1) - 1), 1) if known else None,
            )
        )
    return HandicapEffect(
        MASS_EXPONENT,
        POWER_EXPONENT,
        DRIVER_KG,
        sorted(cars, key=lambda c: c.name),
        drivers,
        _mean([d.model_pct for d in drivers if d.model_pct is not None]),
        _mean([d.measured_pct for d in drivers if d.measured_pct is not None]),
    )


def _lines(season: Season):
    return current_lines(version__result__round__season=season).select_related("version__result")
