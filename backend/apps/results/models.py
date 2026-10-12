from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Attempt, Round, SeasonEntry
from apps.rules.models import RulesVersion
from apps.rules.scoring import PenaltyKind, Status


class RaceResult(models.Model):
    """The race result of one round. Each change makes a new version. Old versions stay."""

    class State(models.TextChoices):
        PROVISIONAL = "provisional", _("Provisional")
        UNDER_REVIEW = "under_review", _("Under review")
        OFFICIAL = "official", _("Official")

    round = models.OneToOneField(Round, on_delete=models.CASCADE, related_name="result")
    status = models.CharField(max_length=14, choices=State.choices, default=State.PROVISIONAL)
    published_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    current_version = models.ForeignKey(
        "ResultVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result of {self.round}"


class ResultVersion(models.Model):
    class Kind(models.TextChoices):
        ENTRY = "entry", _("First entry")
        CORRECTION = "correction", _("Correction")
        PENALTY = "penalty", _("Penalty")

    result = models.ForeignKey(RaceResult, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    rules_version = models.ForeignKey(RulesVersion, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["result", "number"], name="unique_result_version")
        ]

    def __str__(self):
        return f"{self.result} v{self.number}"


class ResultLine(models.Model):
    """One entry in one version. "entered" is what the admin typed. The other fields are the
    final values after the penalties."""

    class LineStatus(models.TextChoices):
        FINISHED = Status.FINISHED, _("Finished")
        DNF = Status.DNF, _("Did not finish")
        DNS = Status.DNS, _("Did not start")
        DSQ = Status.DSQ, _("Disqualified")

    version = models.ForeignKey(ResultVersion, on_delete=models.CASCADE, related_name="lines")
    entry = models.ForeignKey(SeasonEntry, on_delete=models.PROTECT, related_name="result_lines")
    entered_status = models.CharField(max_length=10, choices=LineStatus.choices)
    entered_position = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=LineStatus.choices)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    pole = models.BooleanField(default=False)
    fastest_lap = models.BooleanField(default=False)
    points = models.SmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "entry"], name="unique_entry_per_version")
        ]

    def __str__(self):
        return f"{self.entry} {self.status} {self.position or ''}".strip()


class Protest(models.Model):
    class State(models.TextChoices):
        OPEN = "open", _("Open")
        UPHELD = "upheld", _("Upheld")
        DISMISSED = "dismissed", _("Dismissed")

    result = models.ForeignKey(RaceResult, on_delete=models.CASCADE, related_name="protests")
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.SET_NULL)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    involved = models.ManyToManyField(SeasonEntry, blank=True, related_name="protests")
    lap = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    decision = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Protest {self.id} on {self.result}"


class Penalty(models.Model):
    """A sporting consequence. The result applies all penalties from the entered classification,
    so one penalty never counts two times. An imported penalty keeps its source ID, and the
    same source ID cannot come in again."""

    class Kind(models.TextChoices):
        POSITIONS = PenaltyKind.POSITIONS, _("Lose positions")
        POINTS = PenaltyKind.POINTS, _("Lose points")
        DSQ = PenaltyKind.DSQ, _("Disqualification")

    class Source(models.TextChoices):
        STEWARD = "steward", _("Steward decision")
        IMPORTED = "imported", _("Imported")

    result = models.ForeignKey(RaceResult, on_delete=models.CASCADE, related_name="penalties")
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.SET_NULL)
    entry = models.ForeignKey(SeasonEntry, on_delete=models.PROTECT, related_name="penalties")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.PositiveSmallIntegerField(default=0)
    reason = models.TextField()
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.STEWARD)
    # NULL, not "", so the unique check skips penalties without a source ID.
    external_id = models.CharField(max_length=100, null=True, blank=True)  # noqa: DJ001
    protest = models.ForeignKey(
        Protest, null=True, blank=True, on_delete=models.SET_NULL, related_name="penalties"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["result", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="unique_external_penalty",
            )
        ]

    def __str__(self):
        return f"{self.kind} {self.value} for {self.entry}"
