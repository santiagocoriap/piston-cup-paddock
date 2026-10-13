from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from apps.audit.services import change, record
from apps.competition.attempts import current_attempt, race_session
from apps.competition.models import Attempt, Round, SeasonEntry
from apps.identity.models import DriverProfile

from .models import Restart


class RestartError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _check_responsibility(round_: Round, responsibility: str, entry_ids: list[int]):
    if responsibility == Restart.Responsibility.DRIVERS and not entry_ids:
        raise RestartError("drivers_required")
    if responsibility != Restart.Responsibility.DRIVERS and entry_ids:
        raise RestartError("drivers_not_allowed")
    entries = list(SeasonEntry.objects.filter(season=round_.season, id__in=entry_ids))
    if len(entries) != len(set(entry_ids)):
        raise RestartError("entry_not_in_season")
    return entries


def _names(entries) -> str:
    return ", ".join(sorted(e.driver.display_name for e in entries)) or None


def record_restart(round_: Round, user, *, responsible_entry_ids: list[int], **fields) -> Restart:
    """End the current race attempt as abandoned and start the next one."""
    session = race_session(round_)
    with transaction.atomic():
        attempt = current_attempt(session)
        if attempt.status == Attempt.Status.ACCEPTED:
            raise RestartError("race_already_accepted")
        entries = _check_responsibility(
            round_,
            fields.get("responsibility", Restart.Responsibility.UNKNOWN),
            responsible_entry_ids,
        )
        for key in ("requested_by_id", "executed_by_id"):
            if fields.get(key) and not DriverProfile.objects.filter(pk=fields[key]).exists():
                raise RestartError("driver_not_found")

        attempt.status = Attempt.Status.ABANDONED
        attempt.save(update_fields=["status"])
        replacement = Attempt.objects.create(session=session, number=attempt.number + 1)
        restart = Restart.objects.create(
            abandoned_attempt=attempt, replacement_attempt=replacement, logged_by=user, **fields
        )
        restart.responsible_entries.set(entries)
        record(
            user,
            "restart.recorded",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "attempt": attempt.number,
                "reason": restart.reason,
            },
            changes=[
                change("responsibility", None, restart.responsibility),
                change("responsible_drivers", None, _names(entries)),
                change("review_status", None, restart.review_status),
            ],
            reason=restart.explanation,
        )
    return restart


def update_responsibility(
    restart: Restart,
    user,
    *,
    responsibility: str,
    entry_ids: list[int],
    review_status: str,
    reason: str,
) -> Restart:
    round_ = restart.abandoned_attempt.session.round
    entries = _check_responsibility(round_, responsibility, entry_ids)
    old_entries = list(restart.responsible_entries.select_related("driver"))
    changed = responsibility != restart.responsibility or {e.id for e in old_entries} != {
        e.id for e in entries
    }
    if restart.decided and changed and review_status == Restart.Review.CONFIRMED:
        # A decision that changes after its confirmation is a correction. The audit trail
        # keeps the old decision.
        review_status = Restart.Review.CORRECTED
    with transaction.atomic():
        changes = [
            change("responsibility", restart.responsibility, responsibility),
            change("responsible_drivers", _names(old_entries), _names(entries)),
            change("review_status", restart.review_status, review_status),
        ]
        restart.responsibility = responsibility
        restart.review_status = review_status
        restart.save(update_fields=["responsibility", "review_status"])
        restart.responsible_entries.set(entries)
        record(
            user,
            "restart.reviewed",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "attempt": restart.abandoned_attempt.number,
            },
            changes=[c for c in changes if c["old"] != c["new"]],
            reason=reason,
        )
    return restart


@dataclass
class CausedCount:
    entry_id: int
    driver_name: str
    total: int = 0
    shared: int = 0


@dataclass
class RestartSummary:
    total: int = 0
    caused: list[CausedCount] = field(default_factory=list)
    pending_or_disputed: int = 0
    racing_incident: int = 0
    technical: int = 0
    unknown: int = 0


def summarize(restarts: list[Restart]) -> RestartSummary:
    """Count each restart once. Each confirmed responsible driver gets one count, so the driver
    counts can add up to more than the total when a restart has more than one driver."""
    summary = RestartSummary(total=len(restarts))
    caused: dict[int, CausedCount] = {}
    kinds = Counter()
    for restart in restarts:
        if not restart.decided:
            summary.pending_or_disputed += 1
            continue
        if restart.responsibility != Restart.Responsibility.DRIVERS:
            kinds[restart.responsibility] += 1
            continue
        entries = list(restart.responsible_entries.all())
        for entry in entries:
            row = caused.setdefault(entry.id, CausedCount(entry.id, entry.driver.display_name))
            row.total += 1
            row.shared += 1 if len(entries) > 1 else 0
    summary.racing_incident = kinds[Restart.Responsibility.RACING_INCIDENT]
    summary.technical = kinds[Restart.Responsibility.TECHNICAL]
    summary.unknown = kinds[Restart.Responsibility.UNKNOWN]
    summary.caused = sorted(caused.values(), key=lambda c: (-c.total, c.driver_name))
    return summary


def insert_abandoned_starts(round_: Round, starts: list[dict], user) -> list[Restart]:
    """Add abandoned starts before the current start, for restarts that nobody recorded.

    Each item of `starts` has "seconds" (how long the start lasted) and "explanation". The
    current start stays the last one, also when it is already accepted. Earlier restarts keep
    their place, and the new starts come after them.
    """
    if not starts:
        return []
    session = race_session(round_)
    with transaction.atomic():
        attempts = list(session.attempts.order_by("number"))
        final = current_attempt(session) if not attempts else attempts[-1]
        earlier = [a for a in attempts if a.pk != final.pk]
        new = [Attempt(session=session, number=0, status=Attempt.Status.ABANDONED) for _ in starts]
        # Free the numbers first, because each number must be unique in the session.
        for offset, attempt in enumerate(earlier + [final], start=1000):
            attempt.number = offset
            attempt.save(update_fields=["number"])
        ordered = earlier + new + [final]
        for number, attempt in enumerate(ordered, start=1):
            attempt.number = number
            attempt.save()
        if earlier:
            last_restart = Restart.objects.filter(abandoned_attempt=earlier[-1]).first()
            if last_restart:
                last_restart.replacement_attempt = new[0]
                last_restart.save(update_fields=["replacement_attempt"])
        created = []
        for index, (attempt, item) in enumerate(zip(new, starts, strict=True)):
            replacement = ordered[len(earlier) + index + 1]
            created.append(
                Restart.objects.create(
                    abandoned_attempt=attempt,
                    replacement_attempt=replacement,
                    elapsed_seconds=item.get("seconds"),
                    reason=Restart.Reason.OTHER,
                    explanation=item.get("explanation", ""),
                    logged_by=user,
                )
            )
        record(
            user,
            "restart.imported",
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
