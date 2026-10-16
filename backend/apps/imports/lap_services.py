"""Build the lap tables of a round from the applied result files and the Real Penalty logs."""

from dataclasses import dataclass

from apps.competition.models import Round, Session

from .lap_analysis import DriverLaps, LapRow, analyze, clean_rules_for
from .models import ImportedLap, PenaltyLogFile, ResultImport
from .penalty_services import read_log

LOG_TYPES = {Session.Kind.RACE: "race", Session.Kind.QUALIFYING: "qualifying"}


@dataclass
class DriverInfo:
    entry_id: int
    driver_name: str
    number: int


@dataclass
class RoundLaps:
    session: str
    sessions: list[str]  # The sessions with applied laps.
    has_sectors: bool
    has_pit_data: bool
    clean_rules: list[str]
    drivers: list[tuple[DriverInfo, DriverLaps]]


def _applied_import(round_: Round, kind: str) -> ResultImport | None:
    return (
        ResultImport.objects.filter(
            round=round_, session__kind=kind, status=ResultImport.State.APPLIED
        )
        .order_by("-applied_at")
        .first()
    )


def _log_laps(
    round_: Round, kind: str
) -> tuple[dict[str, dict[int, str]], dict[tuple[str, int], int]] | None:
    """From the last Real Penalty log of the session: for each GUID, the pit status of each lap
    ("in" for a lap with a pit entry, "out" for a lap with only a pit exit), and the cut warnings
    of each (GUID, lap). None when the round has no Real Penalty log of this session.

    The last log is the last start. A start before a restart has its own log, so its pit entries
    and cuts do not count."""
    log_type = LOG_TYPES.get(kind)
    log_file = (
        PenaltyLogFile.objects.filter(round=round_, session_type=log_type)
        .order_by("-started_at")
        .first()
    )
    if log_file is None:
        return None
    log = read_log(log_file)
    pits: dict[str, dict[int, str]] = {}
    for event in log.pits:
        if event.lap is None:
            continue
        laps = pits.setdefault(event.guid, {})
        if event.kind == "entered":
            laps[event.lap] = "in"
        else:
            laps.setdefault(event.lap, "out")
    cuts: dict[tuple[str, int], int] = {}
    for key in log.cut_laps:
        cuts[key] = cuts.get(key, 0) + 1
    return pits, cuts


def _contact_laps(round_: Round) -> set[tuple[str, int]] | None:
    """The (GUID, lap) pairs with an incident in the accepted race start. None when the round
    has no collector events, so no lap can count as clean or not clean by contact."""
    from apps.collectors.incident_api import accepted_race_incidents

    incidents, _, has_events = accepted_race_incidents(round_)
    if not has_events:
        return None
    pairs = set()
    for incident in incidents:
        lap = incident.events[0].lap
        for car in incident.cars:
            if lap is not None:
                pairs.add((car, lap))
    return pairs


def round_laps(round_: Round, kind: str) -> RoundLaps:
    sessions = [
        k
        for k in (Session.Kind.RACE, Session.Kind.QUALIFYING, Session.Kind.PRACTICE)
        if _applied_import(round_, k)
    ]
    result_import = _applied_import(round_, kind)
    race = kind == Session.Kind.RACE
    contacts = _contact_laps(round_) if race else None
    rules = clean_rules_for(race, contacts is not None)
    if result_import is None:
        return RoundLaps(kind, sessions, False, False, rules, [])
    from_log = _log_laps(round_, kind)
    pits, log_cuts = from_log if from_log else ({}, {})
    laps = ImportedLap.objects.filter(result_import=result_import, entry__isnull=False)
    rows: dict[int, list[LapRow]] = {}
    info: dict[int, DriverInfo] = {}
    for lap in laps.select_related("entry__driver"):
        info.setdefault(
            lap.entry_id,
            DriverInfo(lap.entry_id, lap.entry.driver.display_name, lap.entry.number),
        )
        rows.setdefault(lap.entry_id, []).append(
            LapRow(
                lap_number=lap.lap_number,
                time_ms=lap.lap_time_ms,
                sectors_ms=list(lap.sectors_ms or []),
                # AC does not count every cut. Real Penalty warns for more of them.
                cuts=max(lap.cuts, log_cuts.get((lap.guid, lap.lap_number), 0)),
                invalid_reason=lap.invalid_reason,
                tyre=lap.tyre,
                pit=pits.get(lap.guid, {}).get(lap.lap_number),
                contact=(lap.guid, lap.lap_number) in (contacts or set()),
            )
        )
    analyzed = analyze(rows, race=race, contacts=contacts is not None)
    analyzed.sort(key=lambda d: (d.best_lap_ms is None, d.best_lap_ms or 0))
    return RoundLaps(
        session=kind,
        sessions=sessions,
        has_sectors=any(r.sectors_ms for group in rows.values() for r in group),
        has_pit_data=from_log is not None,
        clean_rules=rules,
        drivers=[(info[d.key], d) for d in analyzed],
    )
