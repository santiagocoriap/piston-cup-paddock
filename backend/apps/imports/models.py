from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round, SeasonEntry, Session


def evidence_path(instance, filename):
    return f"results/round-{instance.round_id}/{instance.sha256[:16]}-{filename}"


class ResultImport(models.Model):
    """One uploaded result file. The file stays as evidence, also after the import."""

    class State(models.TextChoices):
        PREVIEW = "preview", _("Preview")
        APPLIED = "applied", _("Applied")

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="imports")
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.SET_NULL, related_name="imports"
    )
    file = models.FileField(upload_to=evidence_path)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64)
    session_type = models.CharField(max_length=12)
    status = models.CharField(max_length=10, choices=State.choices, default=State.PREVIEW)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [
            models.UniqueConstraint(fields=["round", "sha256"], name="unique_file_per_round")
        ]

    def __str__(self):
        return self.filename


class ImportedLap(models.Model):
    """A lap from an applied file. Track records and lap tables read these laps."""

    result_import = models.ForeignKey(ResultImport, on_delete=models.CASCADE, related_name="laps")
    entry = models.ForeignKey(
        SeasonEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="laps"
    )
    guid = models.CharField(max_length=32)
    lap_number = models.PositiveSmallIntegerField()
    lap_time_ms = models.PositiveIntegerField()
    sectors_ms = models.JSONField(default=list)
    cuts = models.PositiveSmallIntegerField(default=0)
    tyre = models.CharField(max_length=10, blank=True)
    ballast_kg = models.PositiveSmallIntegerField(default=0)
    restrictor = models.PositiveSmallIntegerField(default=0)
    timestamp_ms = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["result_import", "guid", "lap_number"]

    def __str__(self):
        return f"{self.guid} lap {self.lap_number}"
