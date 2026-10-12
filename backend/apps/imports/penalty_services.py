"""Upload Real Penalty logs for a round, check them, and apply them.

The rules come from the real race night in samples/:
- Each race log is one start. The last race log (by start time) is the race that counts.
  The other race logs are abandoned starts, and the app records them as restarts.
- Only the penalties of the last start count. An abandoned start also lists time penalties at
  its end, and the app must ignore them.
- A penalty with a serve line was served in the race and does not change the result.
- "Seconds penalty to final time" adds time to the total time.
- An invalid qualifying lap from the log marks the same lap of the qualifying file as invalid.
"""

import hashlib
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.competition.attempts import race_session
from apps.competition.models import Round, Session
from apps.restarts.models import Restart
from apps.restarts.services import insert_abandoned_starts
from apps.results.models import Penalty, RaceResult
from apps.results.services import add_penalty
from apps.rules.scoring import PenaltyKind, ResultError

from .models import ImportedLap, PenaltyLogFile, ResultImport
from .real_penalty import LogPenalty, PenaltyLog, PenaltyLogError, parse, plan_penalties

MAX_BYTES = 2 * 1024 * 1024


def _read(log_file: PenaltyLogFile) -> PenaltyLog:
    with log_file.file.open("rb") as handle:
        return parse(handle.read().decode("utf-8", errors="replace"))


def upload_log(round_: Round, filename: str, content: bytes, user) -> tuple[PenaltyLogFile, bool]:
    if len(content) > MAX_BYTES:
        raise PenaltyLogError("file_too_large")
    log = parse(content.decode("utf-8", errors="replace"))
    sha256 = hashlib.sha256(content).hexdigest()
    existing = PenaltyLogFile.objects.filter(round=round_, sha256=sha256).first()
    if existing:
        return existing, False
    tz = ZoneInfo(round_.season.championship.league.timezone)
    item = PenaltyLogFile(
        round=round_,
        filename=filename[:255],
        sha256=sha256,
        session_type=log.session_type,
        # Real Penalty writes the local time of the server, with no zone: the event timezone.
        started_at=timezone.make_aware(log.started_at, tz),
        ended_at=timezone.make_aware(log.ended_at, tz),
        uploaded_by=user,
    )
    item.file.save(filename, ContentFile(content), save=False)
    item.save()
    return item, True


@dataclass
class PlannedPenalty:
    key: str  # The source ID. The same key never comes in two times.
    kind: str  # "served", "time", "dsq", or "not_served"
    guid: str
    name: str
    entry_id: int | None
    driver_name: str | None
    penalty: str
    cause: str
    lap: int | None
    seconds: int
    already: bool


@dataclass
class PlannedStart:
    filename: str
    seconds: int
    new: bool  # True when the app adds this start as a restart.


@dataclass
class PlannedLap:
    guid: str
    name: str
    lap_time_ms: int
    lap_id: int | None  # None when the qualifying file has no lap with this time.


@dataclass
class PenaltyPreview:
    logs: int
    final_log: str | None
    starts: list[PlannedStart] = field(default_factory=list)
    existing_restarts: int = 0
    penalties: list[PlannedPenalty] = field(default_factory=list)
    ignored_penalties: int = 0  # Penalties of abandoned starts.
    invalid_laps: list[PlannedLap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _entries_by_guid(round_: Round) -> dict[str, object]:
    return {
        e.driver.steam_guid: e
        for e in round_.season.entries.select_related("driver")
        if e.driver.steam_guid
    }


def _planned(item: LogPenalty, kind: str, sha: str, entries, known: set[str]) -> PlannedPenalty:
    detail = item.penalty_id or str(item.seconds) or item.at.isoformat()
    key = f"rp:{sha[:12]}:{item.guid}:{kind}:{detail}"
    entry = entries.get(item.guid)
    return PlannedPenalty(
        key=key,
        kind=kind,
        guid=item.guid,
        name=item.name,
        entry_id=entry.id if entry else None,
        driver_name=entry.driver.display_name if entry else None,
        penalty=item.penalty,
        cause=item.cause,
        lap=item.lap,
        seconds=item.seconds,
        already=key in known,
    )


def preview(round_: Round) -> PenaltyPreview:
    files = list(round_.penalty_logs.order_by("started_at"))
    parsed = {f.id: _read(f) for f in files}
    races = [f for f in files if f.session_type == "race"]
    result = PenaltyPreview(logs=len(files), final_log=races[-1].filename if races else None)
    session = race_session(round_)
    result.existing_restarts = Restart.objects.filter(abandoned_attempt__session=session).count()
    abandoned = races[:-1]
    for index, log_file in enumerate(abandoned):
        result.starts.append(
            PlannedStart(
                filename=log_file.filename,
                seconds=parsed[log_file.id].seconds,
                new=index >= result.existing_restarts,
            )
        )
    if result.existing_restarts and result.existing_restarts < len(abandoned):
        result.warnings.append("some_restarts_recorded")
    if result.existing_restarts > len(abandoned):
        result.warnings.append("more_restarts_than_logs")

    entries = _entries_by_guid(round_)
    known = set(
        Penalty.objects.filter(result__round=round_, external_id__isnull=False).values_list(
            "external_id", flat=True
        )
    )
    if races:
        final = races[-1]
        plan = plan_penalties(parsed[final.id])
        for kind, items in (
            ("served", plan.served),
            ("time", plan.time),
            ("dsq", plan.dsq),
            ("not_served", plan.not_served),
        ):
            for item in items:
                result.penalties.append(_planned(item, kind, final.sha256, entries, known))
        result.ignored_penalties = sum(len(parsed[f.id].penalties) for f in abandoned)
        if any(p.entry_id is None for p in result.penalties):
            result.warnings.append("unmatched_drivers")

    qualifying_laps = ImportedLap.objects.filter(
        result_import__round=round_,
        result_import__session__kind=Session.Kind.QUALIFYING,
        result_import__status=ResultImport.State.APPLIED,
    )
    for log_file in files:
        for lap in parsed[log_file.id].invalid_laps:
            match = qualifying_laps.filter(
                guid=lap.guid,
                lap_time_ms__gte=lap.lap_time_ms - 1,
                lap_time_ms__lte=lap.lap_time_ms + 1,
            ).first()
            result.invalid_laps.append(
                PlannedLap(lap.guid, lap.name, lap.lap_time_ms, match.id if match else None)
            )
    return result


def apply(round_: Round, user, *, penalty_keys: list[str]) -> PenaltyPreview:
    """Add the new restarts, the chosen penalties, and the invalid laps. Then mark the logs."""
    view = preview(round_)
    chosen = [p for p in view.penalties if p.key in set(penalty_keys) and not p.already]
    if any(p.kind == "not_served" for p in chosen):
        raise ResultError("not_served_needs_decision")
    if any(p.entry_id is None for p in chosen):
        raise ResultError("entry_not_in_season")
    result = RaceResult.objects.filter(round=round_).first()
    if chosen and result is None:
        raise ResultError("result_required")

    with transaction.atomic():
        new_starts = [s for s in view.starts if s.new]
        insert_abandoned_starts(
            round_,
            [
                {
                    "seconds": s.seconds,
                    "explanation": f"Real Penalty: {s.filename}",
                }
                for s in new_starts
            ],
            user,
        )
        kinds = {"served": PenaltyKind.SERVED, "time": PenaltyKind.TIME, "dsq": PenaltyKind.DSQ}
        entries = {e.id: e for e in round_.season.entries.all()}
        for item in chosen:
            reason = f"Real Penalty: {item.penalty or item.kind}"
            if item.cause:
                reason += f" ({item.cause})"
            add_penalty(
                result,
                entries[item.entry_id],
                kinds[item.kind],
                item.seconds if item.kind == "time" else 0,
                reason,
                user,
                source=Penalty.Source.REAL_PENALTY,
                external_id=item.key,
            )
        for lap in view.invalid_laps:
            if lap.lap_id:
                ImportedLap.objects.filter(pk=lap.lap_id, invalid_reason="").update(
                    invalid_reason="Real Penalty: invalid qualifying lap"
                )
        round_.penalty_logs.filter(status=ResultImport.State.PREVIEW).update(
            status=ResultImport.State.APPLIED, applied_at=timezone.now()
        )
        record(
            user,
            "penalty_logs.applied",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "restarts": len(new_starts),
                "penalties": len(chosen),
            },
        )
    return preview(round_)
