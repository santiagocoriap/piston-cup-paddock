from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round, SeasonEntry
from apps.rules.models import RulesVersion
from apps.rules.scoring import Status


class RaceResult(models.Model):
    """The race classification of one round. Ticket #10 adds versions and approval."""

    round = models.OneToOneField(Round, on_delete=models.CASCADE, related_name="result")
    rules_version = models.ForeignKey(RulesVersion, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return f"Result of {self.round}"


class ResultLine(models.Model):
    class LineStatus(models.TextChoices):
        FINISHED = Status.FINISHED, _("Finished")
        DNF = Status.DNF, _("Did not finish")
        DNS = Status.DNS, _("Did not start")
        DSQ = Status.DSQ, _("Disqualified")

    result = models.ForeignKey(RaceResult, on_delete=models.CASCADE, related_name="lines")
    entry = models.ForeignKey(SeasonEntry, on_delete=models.PROTECT, related_name="result_lines")
    status = models.CharField(max_length=10, choices=LineStatus.choices)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    pole = models.BooleanField(default=False)
    fastest_lap = models.BooleanField(default=False)
    points = models.SmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["result", "entry"], name="unique_entry_per_result")
        ]

    def __str__(self):
        return f"{self.entry} {self.status} {self.position or ''}".strip()
