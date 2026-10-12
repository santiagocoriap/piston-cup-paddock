"""Read a Real Penalty server log. Pure functions with no database.

Real Penalty writes one log for each session start, also for a start that stops. Each line is
"<date> <time>: <event> - <Key>: <value> - ...". The samples are in samples/*/realpenalty/.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?): (.*)$")
SESSION_TYPES = {"1": "practice", "2": "qualifying", "3": "race"}


class PenaltyLogError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class LogPenalty:
    kind: str  # "new", "taken", "wrong_taken", "time", or "dsq"
    guid: str
    name: str
    at: datetime
    penalty: str = ""  # For example "Drive Through" or "Stop & go 5 seconds".
    cause: str = ""
    lap: int | None = None
    penalty_id: str = ""
    seconds: int = 0


@dataclass
class InvalidLap:
    guid: str
    name: str
    lap_time_ms: int
    at: datetime


@dataclass
class PitEvent:
    kind: str  # "entered" or "left"
    guid: str
    lap: int | None
    at: datetime


@dataclass
class PenaltyLog:
    session_type: str
    track: str
    minutes: int | None
    started_at: datetime
    ended_at: datetime
    ended_normally: bool
    penalties: list[LogPenalty] = field(default_factory=list)
    invalid_laps: list[InvalidLap] = field(default_factory=list)
    cuts: dict[str, int] = field(default_factory=dict)
    pits: list[PitEvent] = field(default_factory=list)

    @property
    def seconds(self) -> int:
        return int((self.ended_at - self.started_at).total_seconds())


def _fields(message: str) -> tuple[str, dict[str, str]]:
    """Split "Event - Key: value - Key: value" into the event and a dict of fields."""
    parts = message.split(" - ")
    values: dict[str, str] = {}
    for part in parts[1:]:
        if ": " in part:
            key, value = part.split(": ", 1)
            values[key.strip()] = value.strip()
        else:
            values.setdefault("_extra", part.strip())
    return parts[0].strip(), values


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "", "None") else None
    except ValueError:
        return None


def parse(text: str) -> PenaltyLog:
    rows = []
    for raw in text.splitlines():
        match = LINE.match(raw.strip())
        if match:
            rows.append((datetime.fromisoformat(match[1]), match[2]))
    if not rows:
        raise PenaltyLogError("not_a_penalty_log")

    header: dict[str, str] = {}
    log = PenaltyLog(
        session_type="",
        track="",
        minutes=None,
        started_at=rows[0][0],
        ended_at=rows[-1][0],
        ended_normally=False,
    )
    in_dsq_block = False
    for at, message in rows:
        if (
            message.startswith(("Track: ", "Type: ", "Time: ", "Laps: ", "Name: "))
            and " - " not in message
        ):
            key, value = message.split(": ", 1)
            header.setdefault(key, value)
            continue
        if message.startswith("DSQ summary"):
            in_dsq_block = True
            continue
        if message.startswith("Time penalty summary") or message.startswith("End session"):
            in_dsq_block = False
            log.ended_normally = log.ended_normally or message.startswith("End session")
            continue

        event, values = _fields(message)
        guid = values.get("GUID", "")
        name = values.get("Name") or values.get("Driver") or ""
        if in_dsq_block and guid:
            # The samples have an empty DSQ block. Any driver line in it counts as a DSQ.
            log.penalties.append(LogPenalty("dsq", guid, name, at))
        elif event == "New penalty":
            log.penalties.append(
                LogPenalty(
                    "new",
                    guid,
                    name,
                    at,
                    penalty=values.get("Penalty", ""),
                    cause=values.get("Cause", ""),
                    lap=_int(values.get("Lap")),
                    penalty_id=values.get("ID", ""),
                )
            )
        elif event in ("Penalty Taken", "Penalty wrong taken"):
            log.penalties.append(
                LogPenalty(
                    "taken" if event == "Penalty Taken" else "wrong_taken",
                    guid,
                    name,
                    at,
                    penalty=values.get("Penalty", ""),
                    lap=_int(values.get("Lap")),
                    penalty_id=values.get("ID", ""),
                )
            )
        elif event == "Seconds penalty to final time":
            log.penalties.append(
                LogPenalty("time", guid, name, at, seconds=_int(values.get("seconds")) or 0)
            )
        elif event == "Invalid Qualify Lap":
            seconds = float(values.get("Time", "0") or 0)
            log.invalid_laps.append(InvalidLap(guid, name, round(seconds * 1000), at))
        elif event in ("Pit lane entered", "Pit lane left") and guid:
            kind = "entered" if event == "Pit lane entered" else "left"
            log.pits.append(PitEvent(kind, guid, _int(values.get("lap") or values.get("Lap")), at))
        elif event in ("Cutting", "Cutting Warning") and guid:
            log.cuts[guid] = log.cuts.get(guid, 0) + 1

    session = SESSION_TYPES.get(header.get("Type", ""))
    if session is None:
        raise PenaltyLogError("unknown_session_type")
    log.session_type = session
    log.track = header.get("Track", "")
    log.minutes = _int(header.get("Time"))
    return log


@dataclass
class PenaltyPlan:
    """What a final race log means for the result."""

    served: list[LogPenalty] = field(default_factory=list)  # Given and served in the race.
    not_served: list[LogPenalty] = field(default_factory=list)  # Given, with no serve line.
    time: list[LogPenalty] = field(default_factory=list)  # Seconds to add to the total time.
    dsq: list[LogPenalty] = field(default_factory=list)


def plan_penalties(log: PenaltyLog) -> PenaltyPlan:
    plan = PenaltyPlan()
    taken = {(p.guid, p.penalty_id) for p in log.penalties if p.kind == "taken"}
    for item in log.penalties:
        if item.kind == "new":
            (plan.served if (item.guid, item.penalty_id) in taken else plan.not_served).append(item)
        elif item.kind == "time":
            plan.time.append(item)
        elif item.kind == "dsq":
            plan.dsq.append(item)
    return plan
