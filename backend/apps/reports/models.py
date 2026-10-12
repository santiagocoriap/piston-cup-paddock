from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round, Season
from apps.results.models import ResultVersion


class RaceReport(models.Model):
    """One generated version of a race report (one round) or a season report (no round).
    A new version never changes an old one. The facts are the only input that the AI gets."""

    class Kind(models.TextChoices):
        RACE = "race", _("Race report")
        SEASON = "season", _("Season report")

    class State(models.TextChoices):
        PENDING = "pending", _("Pending")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")

    class Tone(models.TextChoices):
        SARCASTIC = "sarcastic", _("Sarcastic")
        FRIENDLY = "friendly", _("Friendly")
        ROAST = "roast", _("Roast")

    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.RACE)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="reports")
    round = models.ForeignKey(
        Round, null=True, blank=True, on_delete=models.CASCADE, related_name="reports"
    )
    number = models.PositiveSmallIntegerField()
    source_version = models.ForeignKey(
        ResultVersion, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    result_status = models.CharField(max_length=14)
    language = models.CharField(max_length=5, choices=settings.LANGUAGES)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.SARCASTIC)
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
            models.UniqueConstraint(
                fields=["round", "number"],
                condition=models.Q(kind="race"),
                name="unique_report_number",
            ),
            models.UniqueConstraint(
                fields=["season", "number"],
                condition=models.Q(kind="season"),
                name="unique_season_report_number",
            ),
        ]

    def __str__(self):
        return f"Report {self.number} of {self.round or self.season}"


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
