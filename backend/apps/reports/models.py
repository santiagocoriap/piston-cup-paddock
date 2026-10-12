from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round
from apps.results.models import ResultVersion


class RaceReport(models.Model):
    """One generated version of the race report of a round. A new version never changes an old
    one. The facts are the only input that the AI gets."""

    class State(models.TextChoices):
        PENDING = "pending", _("Pending")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")

    class Tone(models.TextChoices):
        FRIENDLY = "friendly", _("Friendly")
        ROAST = "roast", _("Roast")

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="reports")
    number = models.PositiveSmallIntegerField()
    source_version = models.ForeignKey(
        ResultVersion, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    result_status = models.CharField(max_length=14)
    language = models.CharField(max_length=5, choices=settings.LANGUAGES)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.FRIENDLY)
    prompt_version = models.CharField(max_length=20)
    model = models.CharField(max_length=100)
    facts = models.JSONField()
    status = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    text = models.TextField(blank=True)
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["round", "number"], name="unique_report_number")
        ]

    def __str__(self):
        return f"Report {self.number} of {self.round}"


class ReportRead(models.Model):
    """A user read this report version. A later version stays unread."""

    report = models.ForeignKey(RaceReport, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "user"], name="unique_report_read")
        ]

    def __str__(self):
        return f"{self.user} read {self.report}"
