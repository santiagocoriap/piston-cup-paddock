"""Request, generate, and read race reports and season reports.

The worker generates the text. A failure only marks the report as failed. Results, charts,
and standings never wait for a report.
"""

import logging

import litellm
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.audit.services import record
from apps.competition.models import Round, Season

from .facts import round_facts, season_facts
from .models import RaceReport, ReportRead
from .prompt import PROMPT_VERSION, SEASON_PROMPT_VERSION, messages

logger = logging.getLogger(__name__)

# The cost limit of one report. The model also uses part of it to think before it writes.
MAX_TOKENS = 4000


class ReportError(ValueError):
    pass


def ai_configured() -> bool:
    """True when the provider key of the report model is set, and AI_DISABLED is not on."""
    if settings.AI_DISABLED:
        return False
    try:
        check = litellm.validate_environment(model=settings.AI_REPORT_MODEL)
    except Exception:  # An unknown model counts as not configured.
        return False
    return bool(check.get("keys_in_environment"))


def request_report(round_: Round, user, *, language: str, tone: str) -> RaceReport:
    """Save the facts now and let the worker write the text."""
    if not hasattr(round_, "result"):
        raise ReportError("result_required")
    if round_.reports.filter(status=RaceReport.State.PENDING).exists():
        raise ReportError("report_in_progress")
    facts, version = round_facts(round_)
    with transaction.atomic():
        number = (round_.reports.aggregate(top=Max("number"))["top"] or 0) + 1
        report = RaceReport.objects.create(
            kind=RaceReport.Kind.RACE,
            season=round_.season,
            round=round_,
            number=number,
            source_version=version,
            result_status=facts["result"]["status"] if facts["result"] else "",
            language=language,
            tone=tone,
            prompt_version=PROMPT_VERSION,
            model=settings.AI_REPORT_MODEL,
            facts=facts,
            requested_by=user,
        )
        record(
            user,
            "report.requested",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "report": number,
            },
        )
        transaction.on_commit(lambda: _defer(report.id))
    return report


def request_season_report(season: Season, user, *, language: str, tone: str) -> RaceReport:
    """Save the season facts now and let the worker write the text."""
    reports = season.reports.filter(kind=RaceReport.Kind.SEASON)
    if reports.filter(status=RaceReport.State.PENDING).exists():
        raise ReportError("report_in_progress")
    facts = season_facts(season)
    if not facts["season"]["official_rounds"]:
        raise ReportError("official_rounds_required")
    with transaction.atomic():
        number = (reports.aggregate(top=Max("number"))["top"] or 0) + 1
        report = RaceReport.objects.create(
            kind=RaceReport.Kind.SEASON,
            season=season,
            number=number,
            result_status="finished" if facts["season"]["finished"] else "in_progress",
            language=language,
            tone=tone,
            prompt_version=SEASON_PROMPT_VERSION,
            model=settings.AI_REPORT_MODEL,
            facts=facts,
            requested_by=user,
        )
        record(
            user,
            "report.season_requested",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name, "report": number},
        )
        transaction.on_commit(lambda: _defer(report.id))
    return report


def retry_report(report: RaceReport, user) -> RaceReport:
    """Write a failed report again, with the same facts, prompt, and model."""
    if report.status != RaceReport.State.FAILED:
        raise ReportError("report_not_failed")
    with transaction.atomic():
        report.status = RaceReport.State.PENDING
        report.error = ""
        report.generated_at = None
        report.save(update_fields=["status", "error", "generated_at"])
        record(
            user,
            "report.retried",
            "season",
            report.season_id,
            championship=report.season.championship,
            params={"report": report.number, "season": report.season.name},
        )
        transaction.on_commit(lambda: _defer(report.id))
    return report


def is_outdated(report: RaceReport) -> bool:
    """A race report is outdated when the result has a newer version or a new status. A
    season report is outdated when a result of the season changed after the report."""
    if report.kind == RaceReport.Kind.RACE:
        result = getattr(report.round, "result", None)
        if result is None:
            return False
        return (
            result.current_version_id != report.source_version_id
            or result.status != report.result_status
        )
    from apps.results.models import RaceResult

    return RaceResult.objects.filter(
        round__season=report.season, updated_at__gt=report.created_at
    ).exists()


def regenerate(report: RaceReport, user) -> RaceReport:
    """A new version of the report with the same language and tone, from the current facts."""
    if report.kind == RaceReport.Kind.RACE:
        return request_report(report.round, user, language=report.language, tone=report.tone)
    return request_season_report(report.season, user, language=report.language, tone=report.tone)


def _defer(report_id: int) -> None:
    from .tasks import generate_report

    generate_report.defer(report_id=report_id)


def auto_request(round_: Round, user) -> RaceReport | None:
    """A report after the approval. It does nothing when the AI has no key."""
    if not ai_configured():
        return None
    try:
        return request_report(round_, user, language=settings.LANGUAGE_CODE, tone="sarcastic")
    except ReportError:
        return None


def generate(report_id: int) -> RaceReport:
    report = RaceReport.objects.get(pk=report_id)
    if report.status != RaceReport.State.PENDING:
        return report
    if not ai_configured():
        return _fail(report, "ai_not_configured")
    try:
        response = litellm.completion(
            model=report.model,
            messages=messages(
                report.facts,
                report.language,
                report.tone,
                season=report.kind == RaceReport.Kind.SEASON,
            ),
            max_tokens=MAX_TOKENS,
            timeout=120,
            num_retries=2,
            extra_headers=_headers(),
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
    except Exception as error:  # Any provider error only fails this report.
        logger.warning("Report %s failed: %s", report.id, error)
        return _fail(report, _error_code(error))
    if not text:
        return _fail(report, "ai_empty_text")
    if getattr(choice, "finish_reason", None) == "length":
        return _fail(report, "ai_text_cut")
    report.text = text
    report.status = RaceReport.State.READY
    report.generated_at = timezone.now()
    report.save(update_fields=["text", "status", "generated_at"])
    _notify_ready(report)
    return report


def _notify_ready(report: RaceReport) -> None:
    from apps.community.services import notify, round_params, season_user_ids

    if report.round:
        params, link = round_params(report.round), f"/rounds/{report.round_id}"
    else:
        params = {"championship": report.season.championship.name, "season": report.season.name}
        link = f"/seasons/{report.season_id}"
    notify(season_user_ids(report.season), f"report.ready.{report.kind}", params, link)


# Fixed codes for the admin list. The full provider text goes only to the worker log.
ERROR_CODES = {
    "AuthenticationError": "ai_key_refused",
    "PermissionDeniedError": "ai_key_refused",
    "BadRequestError": "ai_request_refused",
    "RateLimitError": "ai_rate_limit",
    "Timeout": "ai_timeout",
    "APIConnectionError": "ai_no_connection",
}


def _error_code(error: Exception) -> str:
    return ERROR_CODES.get(type(error).__name__, "ai_error")


def _headers() -> dict[str, str] | None:
    if settings.ANTHROPIC_WORKSPACE_ID:
        return {"anthropic-workspace-id": settings.ANTHROPIC_WORKSPACE_ID}
    return None


def _fail(report: RaceReport, error: str) -> RaceReport:
    report.status = RaceReport.State.FAILED
    report.error = error
    report.generated_at = timezone.now()
    report.save(update_fields=["status", "error", "generated_at"])
    return report


def latest_ready(round_ids) -> dict[int, RaceReport]:
    """The newest ready report of each round."""
    latest: dict[int, RaceReport] = {}
    for report in RaceReport.objects.filter(
        kind=RaceReport.Kind.RACE, round_id__in=round_ids, status=RaceReport.State.READY
    ).order_by("round_id", "-number"):
        latest.setdefault(report.round_id, report)
    return latest


def read_ids(user, reports) -> set[int]:
    return set(
        ReportRead.objects.filter(user=user, report__in=reports).values_list("report_id", flat=True)
    )


def mark_read(report: RaceReport, user) -> None:
    ReportRead.objects.get_or_create(report=report, user=user)
