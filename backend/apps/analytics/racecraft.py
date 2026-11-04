"""Overtakes and battles on the track, from the positions that the server collector records.

Each car has samples of its place on the lap. The sum of laps and place is the progress of the car
in the race, so the app can compare 2 cars at any time, not only at the line. The rules:

- An overtake: car A is behind car B for at least STABLE_S seconds, then ahead of it for at least
  STABLE_S seconds. So a car that goes side by side for a moment does not count.
- An overtake does not count when the other car stopped or is slow (a spin, a crash, a pit stop):
  its speed is below SLOW_SHARE of its normal speed in the seconds before.
- A lapped car is one full lap away, so its progress does not cross: a lap down is not an overtake.
- A battle: 2 cars within BATTLE_LAPS of a lap of each other for at least BATTLE_S seconds.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median

from django.core.cache import cache
from django.db.models import Max

from apps.collectors.models import CollectorEvent
from apps.competition.models import Round
from apps.identity.models import by_guid

RACE = 3  # The AC session type of a race.
CACHE_SECONDS = 3600
WINDOW = timedelta(hours=12)
STEP_S = 1  # The app compares the cars one time each second.
MAX_SAMPLE_GAP_S = 3  # A car with no sample for this long has no value here.
STABLE_S = 5
SLOW_SHARE = 0.5
BATTLE_S = 10
# About 1 second on a lap of 100 seconds. The gap is a part of a lap, as the app has no timing here.
BATTLE_LAPS = 0.01


@dataclass
class Overtake:
    at_s: int
    lap: int
    attacker: object
    defender: object
    x: float | None = None
    z: float | None = None


@dataclass
class Battle:
    a: object  # The car behind at the start.
    b: object
    start_s: int
    seconds: int
    passed: bool


@dataclass
class Racecraft:
    overtakes: list[Overtake] = field(default_factory=list)
    battles: list[Battle] = field(default_factory=list)


def progress_track(samples: list[tuple[float, float, float, float]]) -> dict[int, tuple]:
    """For each second: (progress, x, z). A sample is (seconds, x, z, place on the lap). Progress
    only goes on at the line, so a car that resets to the pits does not gain a lap."""
    track: dict[int, tuple] = {}
    ordered = sorted(samples)
    # A car on the grid starts before the line, so its first crossing is the start of lap 1.
    laps = -1 if ordered and ordered[0][3] > 0.5 else 0
    before = None
    for at, x, z, spline in ordered:
        if before is not None:
            if before - spline > 0.5:
                laps += 1
            elif spline - before > 0.5:
                laps -= 1  # The car went back over the line.
        before = spline
        track[int(at)] = (laps + spline, x, z)
    filled: dict[int, tuple] = {}
    keys = sorted(track)
    for now, after in zip(keys, keys[1:] + keys[-1:], strict=True):
        filled[now] = track[now]
        if after - now > MAX_SAMPLE_GAP_S:
            continue
        for second in range(now + 1, after):
            share = (second - now) / (after - now)
            filled[second] = (
                track[now][0] + (track[after][0] - track[now][0]) * share,
                track[now][1],
                track[now][2],
            )
    return filled


def _normal_rate(track: dict[int, tuple]) -> float:
    times = sorted(track)
    rates = [
        track[b][0] - track[a][0] for a, b in zip(times, times[1:], strict=False) if b - a == 1
    ]
    return median(rates) if rates else 0.0


def analyze(tracks: dict[object, dict[int, tuple]]) -> Racecraft:
    result = Racecraft()
    keys = sorted(tracks, key=str)
    rates = {key: _normal_rate(tracks[key]) for key in keys}

    def slow(key, second: int) -> bool:
        track = tracks[key]
        then = track.get(second - STABLE_S)
        now = track.get(second)
        if then is None or now is None or rates[key] <= 0:
            return True
        return (now[0] - then[0]) / STABLE_S < rates[key] * SLOW_SHARE

    for index, a in enumerate(keys):
        for b in keys[index + 1 :]:
            shared = sorted(set(tracks[a]) & set(tracks[b]))
            run_sign = 0
            run_start = None
            before_sign = 0  # The sign of the last stable run.
            battle_start = None
            for position, second in enumerate(shared):
                gap = tracks[a][second][0] - tracks[b][second][0]
                sign = 1 if gap > 0 else -1
                if sign != run_sign or (position and second - shared[position - 1] > 1):
                    run_sign, run_start = sign, second
                if second - run_start == STABLE_S:
                    if before_sign and sign != before_sign:
                        attacker, defender = (a, b) if sign > 0 else (b, a)
                        if not slow(defender, run_start) and not slow(attacker, run_start):
                            spot = tracks[attacker].get(run_start, (0, None, None))
                            result.overtakes.append(
                                Overtake(
                                    at_s=run_start,
                                    lap=int(tracks[attacker][run_start][0]) + 1,
                                    attacker=attacker,
                                    defender=defender,
                                    x=spot[1],
                                    z=spot[2],
                                )
                            )
                    before_sign = sign
                near = abs(gap) <= BATTLE_LAPS
                if near and battle_start is None:
                    battle_start = (second, gap)
                if battle_start and (not near or position == len(shared) - 1):
                    start, first_gap = battle_start
                    if second - start >= BATTLE_S:
                        behind, ahead = (a, b) if first_gap < 0 else (b, a)
                        passed = any(
                            o.attacker == behind
                            and o.defender == ahead
                            and start <= o.at_s <= second
                            for o in result.overtakes
                        )
                        result.battles.append(Battle(behind, ahead, start, second - start, passed))
                    battle_start = None
    result.overtakes.sort(key=lambda o: o.at_s)
    return result


def round_racecraft(round_: Round) -> tuple[bool, Racecraft, dict]:
    """(has positions, the racecraft, the entry of each car) for the last race start of a round."""
    if round_.scheduled_at is None:
        return False, Racecraft(), {}
    around = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
    )
    starts = [
        e.occurred_at
        for e in around.filter(kind="session_started").order_by("occurred_at")
        if (e.data or {}).get("type") == RACE
    ]
    if not starts:
        return False, Racecraft(), {}
    start = starts[-1]
    end = (
        around.filter(kind="session_started", occurred_at__gt=start)
        .order_by("occurred_at")
        .values_list("occurred_at", flat=True)
        .first()
    )
    events = around.filter(kind="positions", occurred_at__gte=start)
    if end:
        events = events.filter(occurred_at__lt=end)
    # The result reads all the positions of a race, so the app keeps it until new events come.
    newest = events.aggregate(newest=Max("id"))["newest"]
    key = f"racecraft:{round_.id}:{newest}:{round_.season.entries.count()}"
    if (found := cache.get(key)) is not None:
        return found
    raw: dict[str, list[tuple[float, float, float, float]]] = {}
    for event in events.order_by("occurred_at").iterator():
        base = (event.occurred_at - start).total_seconds()
        for car, samples in (event.data or {}).get("cars", {}).items():
            for sample in samples:
                if len(sample) >= 4:
                    raw.setdefault(car, []).append(
                        (
                            base + sample[0] / 1000,
                            float(sample[1]),
                            float(sample[2]),
                            float(sample[3]),
                        )
                    )
    if not raw:
        return False, Racecraft(), {}
    entries = by_guid(round_.season.entries.select_related("driver"))
    tracks = {car: progress_track(samples) for car, samples in raw.items() if car in entries}
    result = (True, analyze(tracks), {car: entries[car] for car in tracks})
    cache.set(key, result, CACHE_SECONDS)
    return result
