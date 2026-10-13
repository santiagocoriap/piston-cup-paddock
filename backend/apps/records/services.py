"""Read the laps from the database and decide which laps can be records.

The rules for the first release (docs/LEAGUE_RULES.md):
- Only laps from rounds with an official race result count.
- Qualifying laps and laps from the accepted race start count. Abandoned starts do not.
- An invalid lap (a cut, or marked by an admin) and the race laps of a DSQ driver cannot be
  records. They stay in the history with the reason.
"""

from datetime import UTC, datetime, time

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.competition.models import Attempt, Session
from apps.competition.permissions import visible_championships
from apps.imports.models import ImportedLap, ResultImport
from apps.results.models import RaceResult
from apps.rules.scoring import Status

from .boards import RecordLap, boards
from .models import ManualRecord

CATEGORIES = {Session.Kind.QUALIFYING: "qualifying", Session.Kind.RACE: "race"}


def _dsq_entries(result: RaceResult) -> set[int]:
    if result.current_version is None:
        return set()
    return set(
        result.current_version.lines.filter(status=Status.DSQ).values_list("entry_id", flat=True)
    )


def _reason(lap: ImportedLap, category: str, dsq: set[int]) -> str | None:
    if lap.invalid_reason:
        return "invalid"
    if lap.cuts > 0:
        return "cut"
    if category == "race":
        attempt = lap.result_import.attempt
        if attempt is not None and attempt.status != Attempt.Status.ACCEPTED:
            return "abandoned_attempt"
        if lap.entry_id in dsq:
            return "dsq"
    return None


def candidate_laps(user, layout_id: int | None = None) -> tuple[list[RecordLap], dict]:
    """The laps that the user can see, with the reason when a lap cannot be a record.
    The second value maps a lap ID to the stored lap, for the details. With user None, all
    laps count: the reports use this, because a record does not depend on the reader."""
    laps = ImportedLap.objects.filter(
        entry__isnull=False,
        result_import__status=ResultImport.State.APPLIED,
        result_import__session__kind__in=list(CATEGORIES),
        result_import__round__result__status=RaceResult.State.OFFICIAL,
    )
    if user is not None:
        laps = laps.filter(
            result_import__round__season__championship__in=visible_championships(user)
        )
    laps = laps.select_related(
        "entry__driver",
        "entry__car",
        "result_import__attempt",
        "result_import__session",
        "result_import__uploaded_by",
        "result_import__round__season__championship",
        "result_import__round__track_layout__track",
        "result_import__round__result__current_version",
    )
    if layout_id is not None:
        laps = laps.filter(result_import__round__track_layout_id=layout_id)

    dsq_by_round: dict[int, set[int]] = {}
    items, details = [], {}
    for lap in laps:
        round_ = lap.result_import.round
        if round_.id not in dsq_by_round:
            dsq_by_round[round_.id] = _dsq_entries(round_.result)
        category = CATEGORIES[lap.result_import.session.kind]
        items.append(
            RecordLap(
                lap_id=lap.id,
                layout_id=round_.track_layout_id,
                car_id=lap.entry.car_id,
                category=category,
                lap_time_ms=lap.lap_time_ms,
                entry_id=lap.entry_id,
                driver_name=lap.entry.driver.display_name,
                round_id=round_.id,
                round_number=round_.number,
                date=round_.scheduled_at or lap.result_import.uploaded_at,
                timestamp_ms=lap.timestamp_ms,
                ineligible_reason=_reason(lap, category, dsq_by_round[round_.id]),
                season_id=round_.season_id,
            )
        )
        details[lap.id] = lap
    return items, details


def manual_laps(user, layout_id: int | None = None) -> tuple[list[RecordLap], dict]:
    """Manual records as record laps. A negative lap ID and entry ID mark them."""
    items = ManualRecord.objects.select_related("layout__track", "car", "championship")
    if user is not None:
        items = items.filter(championship__in=visible_championships(user))
    if layout_id is not None:
        items = items.filter(layout_id=layout_id)
    laps, details = [], {}
    for item in items:
        laps.append(
            RecordLap(
                lap_id=-item.id,
                layout_id=item.layout_id,
                car_id=item.car_id,
                category=item.category,
                lap_time_ms=item.lap_time_ms,
                entry_id=-item.id,
                driver_name=item.driver_name,
                round_id=0,
                round_number=0,
                date=datetime.combine(item.date, time(), tzinfo=UTC),
                timestamp_ms=0,
            )
        )
        details[-item.id] = item
    return laps, details


def record_boards(
    user,
    layout_id: int | None = None,
    *,
    car_id: int | None = None,
    category: str | None = None,
    season_id: int | None = None,
    overall: bool = False,
):
    """The boards with filters. A season filter leaves out manual records, which have no
    season."""
    laps, details = candidate_laps(user, layout_id)
    if season_id is None:
        manual, manual_details = manual_laps(user, layout_id)
        laps += manual
        details.update(manual_details)
    else:
        laps = [lap for lap in laps if lap.season_id == season_id]
    if car_id is not None:
        laps = [lap for lap in laps if lap.car_id == car_id]
    if category is not None:
        laps = [lap for lap in laps if lap.category == category]
    return boards(laps, overall=overall), details


def invalidate_lap(lap: ImportedLap, reason: str, user) -> ImportedLap:
    round_ = lap.result_import.round
    with transaction.atomic():
        lap.invalid_reason = reason
        lap.save(update_fields=["invalid_reason"])
        record(
            user,
            "lap.invalidated",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "driver": lap.entry.driver.display_name if lap.entry else lap.guid,
                "number": round_.number,
                "track": str(round_.track_layout),
                "lap": lap.lap_number,
                "time_ms": lap.lap_time_ms,
                "at": timezone.now().isoformat(),
            },
            reason=reason,
        )
    return lap
