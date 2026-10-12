"""Request, generate, and read race reports.

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
from apps.competition.models import Round

from .facts import round_facts
from .models import RaceReport, ReportRead
from .prompt import PROMPT_VERSION, messages

logger = logging.getLogger(__name__)

MAX_TOKENS = 1500  # The cost limit of one report.


class ReportError(ValueError):
    pass


def ai_configured() -> bool:
    """True when the provider key of the report model is set."""
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


def _defer(report_id: int) -> None:
    from .tasks import generate_report

    generate_report.defer(report_id=report_id)


def auto_request(round_: Round, user) -> RaceReport | None:
    """A report after the approval. It does nothing when the AI has no key."""
    if not ai_configured():
        return None
    try:
        return request_report(round_, user, language=settings.LANGUAGE_CODE, tone="friendly")
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
            messages=messages(report.facts, report.language, report.tone),
            max_tokens=MAX_TOKENS,
            timeout=120,
            num_retries=2,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as error:  # Any provider error only fails this report.
        logger.warning("Report %s failed: %s", report.id, error)
        return _fail(report, f"ai_error: {type(error).__name__}")
    if not text:
        return _fail(report, "ai_empty_text")
    report.text = text
    report.status = RaceReport.State.READY
    report.generated_at = timezone.now()
    report.save(update_fields=["text", "status", "generated_at"])
    return report


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
        round_id__in=round_ids, status=RaceReport.State.READY
    ).order_by("round_id", "-number"):
        latest.setdefault(report.round_id, report)
    return latest


def read_ids(user, reports) -> set[int]:
    return set(
        ReportRead.objects.filter(user=user, report__in=reports).values_list("report_id", flat=True)
    )


def mark_read(report: RaceReport, user) -> None:
    ReportRead.objects.get_or_create(report=report, user=user)
