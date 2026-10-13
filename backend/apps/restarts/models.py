from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Attempt, SeasonEntry
from apps.identity.models import DriverProfile


class Restart(models.Model):
    """A restart decision. It records what happened. It does not decide if a restart was allowed."""

    class Reason(models.TextChoices):
        FIRST_LAP_CRASH = "first_lap_crash", _("First-lap crash")
        TECHNICAL_ISSUE = "technical_issue", _("Technical issue")
        SERVER_PROBLEM = "server_problem", _("Server problem")
        WRONG_CONFIGURATION = "wrong_configuration", _("Wrong configuration")
        FALSE_START = "false_start", _("False start")
        OTHER = "other", _("Other")

    class Responsibility(models.TextChoices):
        DRIVERS = "drivers", _("One or more drivers")
        RACING_INCIDENT = "racing_incident", _("Racing incident")
        TECHNICAL = "technical", _("Technical cause")
        UNKNOWN = "unknown", _("Unknown")

    class Review(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CORRECTED = "corrected", _("Corrected after confirmation")
        DISPUTED = "disputed", _("Disputed")

    abandoned_attempt = models.OneToOneField(
        Attempt, on_delete=models.CASCADE, related_name="restart"
    )
    replacement_attempt = models.OneToOneField(
        Attempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="replaces"
    )
    lap = models.PositiveSmallIntegerField(null=True, blank=True)
    elapsed_seconds = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    explanation = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        DriverProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    executed_by = models.ForeignKey(
        DriverProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    responsibility = models.CharField(
        max_length=16, choices=Responsibility.choices, default=Responsibility.UNKNOWN
    )
    responsible_entries = models.ManyToManyField(
        SeasonEntry, blank=True, related_name="restarts_caused"
    )
    review_status = models.CharField(max_length=10, choices=Review.choices, default=Review.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["abandoned_attempt__number"]

    def __str__(self):
        return f"Restart after {self.abandoned_attempt}"

    @property
    def decided(self) -> bool:
        """A confirmed or corrected decision counts in the statistics."""
        return self.review_status in (self.Review.CONFIRMED, self.Review.CORRECTED)
