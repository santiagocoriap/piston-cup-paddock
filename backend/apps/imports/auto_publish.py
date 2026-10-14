"""Publish the files of the server collector with no admin click, when they have no problem.

A result file becomes a provisional result. An admin still approves the official result.
A file with a problem waits for an admin, with the reasons. See
docs/adr/0002-collector-automation.md and phase 1 of docs/plans/ac-integration.md.
"""

import logging
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.audit.services import record
from apps.community.services import notify, round_params, staff_user_ids
from apps.competition.models import Round
from apps.results.models import RaceResult
from apps.rules.scoring import ResultError

from . import penalty_services
from .ac_results import ResultFileError
from .models import ResultImport
from .services import apply, preview

log = logging.getLogger(__name__)

# The audit log shows this name as the actor of an automatic step.
COLLECTOR = SimpleNamespace(username="collector", is_authenticated=False)

# Row warnings that stop the automatic apply. "fewer_laps" does not stop it: the row gets the
# status "finished", and the admin checks a possible DNF.
BLOCKING_ROW_WARNINGS = {"guid_differs_in_result", "car_differs", "handicap_differs"}

# The final Real Penalty log of the race ends close to the end of the race file.
FINAL_LOG_WINDOW = timedelta(minutes=10)
RESULT_NAME = re.compile(r"(\d{4})_(\d{1,2})_(\d{1,2})_(\d{1,2})_(\d{1,2})_")


def _reasons(result_import: ResultImport) -> list[str]:
    view = preview(result_import)
    reasons = set(view.warnings)
    if view.unmatched:
        reasons.add("unmatched_drivers")
    for row in view.drivers:
        reasons.update(w for w in row.warnings if w in BLOCKING_ROW_WARNINGS)
    if (
        view.session_type == "race"
        and RaceResult.objects.filter(round=result_import.round).exists()
    ):
        # A second race file is a change of a result, so an admin decides.
        reasons.add("result_exists")
    return sorted(reasons)


def _block(result_import: ResultImport, reasons: list[str]) -> None:
    result_import.auto_status = ResultImport.AutoState.BLOCKED
    result_import.auto_reasons = reasons
    result_import.save(update_fields=["auto_status", "auto_reasons"])
    round_ = result_import.round
    notify(
        staff_user_ids(round_.season, "results"),
        "import.blocked",
        {**round_params(round_), "file": result_import.filename},
        f"/rounds/{round_.id}",
    )


def auto_apply(result_import: ResultImport) -> None:
    """Apply a collector file when the championship allows it and the preview is clean."""
    round_ = result_import.round
    if not round_.season.championship.auto_publish_results:
        return
    if result_import.status == ResultImport.State.APPLIED:
        return
    reasons = _reasons(result_import)
    if reasons:
        _block(result_import, reasons)
        return
    view = preview(result_import)
    try:
        with transaction.atomic():
            apply(result_import, None, statuses={}, ignored=[])
            result_import.auto_status = ResultImport.AutoState.APPLIED
            result_import.auto_reasons = []
            result_import.review_flags = [
                {"entry_id": row.entry_id, "code": "fewer_laps"}
                for row in view.drivers
                if "fewer_laps" in row.warnings
            ]
            result_import.save(update_fields=["auto_status", "auto_reasons", "review_flags"])
            record(
                COLLECTOR,
                "import.auto_applied",
                "round",
                round_.id,
                championship=round_.season.championship,
                params={
                    "number": round_.number,
                    "file": result_import.filename,
                    "session": view.session_type,
                },
            )
    except (ResultFileError, ResultError) as error:
        _block(result_import, [getattr(error, "code", "not_applied")])
        return
    if view.session_type == "race":
        auto_penalties(round_)


def _race_end(result_import: ResultImport) -> datetime | None:
    """The end of the race, from the name of the result file, in the league timezone."""
    match = RESULT_NAME.search(result_import.filename)
    if not match:
        return None
    tz = ZoneInfo(result_import.round.season.championship.league.timezone)
    year, month, day, hour, minute = (int(v) for v in match.groups())
    return datetime(year, month, day, hour, minute, tzinfo=tz)


def auto_penalties(round_: Round) -> None:
    """Add the restarts and the served penalties of the Real Penalty logs.

    Only after the race result is applied, and only when the final race log is here: the final
    log ends near the end of the race file. A time penalty, a disqualification, and a penalty
    that the driver did not serve wait for an admin.
    """
    if not round_.season.championship.auto_publish_results:
        return
    race = (
        round_.imports.filter(session_type="race", status=ResultImport.State.APPLIED)
        .order_by("-applied_at")
        .first()
    )
    if race is None or not round_.penalty_logs.filter(status=ResultImport.State.PREVIEW).exists():
        return
    end = _race_end(race)
    races = list(round_.penalty_logs.filter(session_type="race").order_by("started_at"))
    if end is None or not races or races[-1].ended_at < end - FINAL_LOG_WINDOW:
        return  # The final log is not here yet. The collector sends it later.
    view = penalty_services.preview(round_)
    if view.warnings:
        return  # An admin checks the logs on the round page.
    served = [p.key for p in view.penalties if p.kind == "served" and not p.already]
    try:
        with transaction.atomic():
            penalty_services.apply(round_, None, penalty_keys=served)
            record(
                COLLECTOR,
                "penalty_logs.auto_applied",
                "round",
                round_.id,
                championship=round_.season.championship,
                params={"number": round_.number, "penalties": len(served)},
            )
    except ResultError:
        log.exception("Automatic penalty import failed for round %s", round_.id)
