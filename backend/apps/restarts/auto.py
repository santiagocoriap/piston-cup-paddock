"""Restarts from the race starts that the server collector saw.

Each race start of the collector is one start of the race. Each start before the last one is a
restart. The app creates the restarts that nobody recorded, with a responsible driver from the
league rules:

- A bad launch: Real Penalty gives a jump start penalty. The driver with the penalty causes the
  restart. Real Penalty writes one log for each start, so the logs and the starts go in order.
- An accident: the driver of the first collision of the start causes the restart.

The responsible driver is a suggestion: the review status stays "pending" for a steward.
"""

from django.db import transaction

from apps.audit.services import record
from apps.competition.attempts import race_session
from apps.competition.models import Round
from apps.identity.models import by_guid
from apps.imports.penalty_services import read_log

from .models import Restart
from .services import insert_abandoned_starts

AUTO_NOTE = "La app creó este reinicio con las largadas del colector."
JUMP_CAUSE = "jump"


def _jump_starts(round_: Round, starts: int) -> dict[int, list[str]]:
    """For each start number: the GUIDs with a jump start penalty. Log N is start N, in time
    order. The log of the final start can be missing (it uploads later), so fewer logs than
    starts still match. More logs than starts do not: then the order is not sure."""
    logs = list(round_.penalty_logs.filter(session_type="race").order_by("started_at"))
    if len(logs) > starts:
        return {}
    found = {}
    for number, log_file in enumerate(logs, start=1):
        log = read_log(log_file)
        guids = [
            p.guid
            for p in log.penalties
            if p.kind == "new" and JUMP_CAUSE in (p.cause or "").lower()
        ]
        if guids:
            found[number] = list(dict.fromkeys(guids))
    return found


def _assign(round_: Round, restarts: list[Restart], starts: int) -> None:
    """Set the reason and the responsible drivers of restarts from the evidence."""
    from .api import _collector_evidence

    evidence = _collector_evidence(round_)
    jumps = _jump_starts(round_, starts)
    entries = by_guid(round_.season.entries.select_related("driver"))
    for restart in restarts:
        number = restart.abandoned_attempt.number
        jumpers = [entries[g] for g in jumps.get(number, []) if g in entries]
        suggested = evidence.get(number, ([], []))[1]
        if jumpers:
            reason = Restart.Reason.FALSE_START
            responsible = jumpers
        elif suggested:
            reason = Restart.Reason.FIRST_LAP_CRASH
            responsible = [e for e in entries.values() if e.id == suggested[0].entry_id][:1]
        else:
            reason = Restart.Reason.OTHER
            responsible = []
        responsibility = (
            Restart.Responsibility.DRIVERS if responsible else Restart.Responsibility.UNKNOWN
        )
        same = (
            restart.reason == reason
            and restart.responsibility == responsibility
            and {e.id for e in restart.responsible_entries.all()} == {e.id for e in responsible}
        )
        if same:
            continue  # Most views: nothing new, so no write.
        restart.reason = reason
        restart.responsibility = responsibility
        restart.responsible_entries.set(responsible)
        restart.save(update_fields=["reason", "responsibility"])


def _unreviewed(session) -> list[Restart]:
    """The restarts that the app made and that nobody reviewed or changed yet. New evidence (a
    log that comes later) can still change them."""
    return list(
        Restart.objects.filter(
            abandoned_attempt__session=session,
            logged_by__isnull=True,
            explanation=AUTO_NOTE,
            review_status="pending",
        ).select_related("abandoned_attempt")
    )


def sync_restarts(round_: Round) -> list[Restart]:
    """Create the restarts of the collector starts that the round does not have yet. Update
    the suggestion of the app restarts that nobody reviewed when the race logs change."""
    from .api import _start_times

    starts = _start_times(round_)
    session = race_session(round_)
    have = session.attempts.count()
    if len(starts) < 2:
        return []
    if have >= len(starts):
        logs = round_.penalty_logs.filter(session_type="race").count()
        unreviewed = _unreviewed(session)
        if logs and unreviewed:
            with transaction.atomic():
                _assign(round_, unreviewed, len(starts))
        return []
    times = [starts[n] for n in sorted(starts)]
    new_numbers = list(range(max(have, 1), len(starts)))  # The abandoned starts to add.
    with transaction.atomic():
        created = insert_abandoned_starts(
            round_,
            [
                {
                    "seconds": int((times[n] - times[n - 1]).total_seconds()),
                    "explanation": AUTO_NOTE,
                }
                for n in new_numbers
            ],
            None,
        )
        _assign(round_, created, len(starts))
        record(
            None,
            "restart.detected",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "count": len(created),
            },
        )
    return created
