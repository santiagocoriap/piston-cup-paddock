"""Build the lap tables of a round from the applied result files and the Real Penalty logs."""

from dataclasses import dataclass

from apps.competition.models import Round, Session

from .lap_analysis import CLEAN_RULES, DriverLaps, LapRow, analyze
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


def _pit_laps(round_: Round, kind: str) -> dict[str, dict[int, str]] | None:
    """For each GUID, the pit status of each lap: "in" for a lap with a pit entry, "out" for a
    lap with only a pit exit. None when the round has no Real Penalty log of this session."""
    log_type = LOG_TYPES.get(kind)
    log_file = (
        PenaltyLogFile.objects.filter(round=round_, session_type=log_type)
        .order_by("-started_at")
        .first()
    )
    if log_file is None:
        return None
    pits: dict[str, dict[int, str]] = {}
    for event in read_log(log_file).pits:
        if event.lap is None:
            continue
        laps = pits.setdefault(event.guid, {})
        if event.kind == "entered":
            laps[event.lap] = "in"
        else:
            laps.setdefault(event.lap, "out")
    return pits


def round_laps(round_: Round, kind: str) -> RoundLaps:
    sessions = [
        k
        for k in (Session.Kind.RACE, Session.Kind.QUALIFYING, Session.Kind.PRACTICE)
        if _applied_import(round_, k)
    ]
    result_import = _applied_import(round_, kind)
    race = kind == Session.Kind.RACE
    rules = CLEAN_RULES if race else CLEAN_RULES[:3]
    if result_import is None:
        return RoundLaps(kind, sessions, False, False, rules, [])
    pits = _pit_laps(round_, kind)
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
                cuts=lap.cuts,
                invalid_reason=lap.invalid_reason,
                tyre=lap.tyre,
                pit=(pits or {}).get(lap.guid, {}).get(lap.lap_number),
            )
        )
    analyzed = analyze(rows, race=race)
    analyzed.sort(key=lambda d: (d.best_lap_ms is None, d.best_lap_ms or 0))
    return RoundLaps(
        session=kind,
        sessions=sessions,
        has_sectors=any(r.sectors_ms for group in rows.values() for r in group),
        has_pit_data=pits is not None,
        clean_rules=rules,
        drivers=[(info[d.key], d) for d in analyzed],
    )
