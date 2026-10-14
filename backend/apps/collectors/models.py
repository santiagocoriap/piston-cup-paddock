from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Championship, Round


class CollectorToken(models.Model):
    """The key of one server collector. It can only send files and events for one championship.
    The app keeps only a hash of the key."""

    championship = models.ForeignKey(
        Championship, on_delete=models.CASCADE, related_name="collectors"
    )
    name = models.CharField(max_length=60)
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # The Content Manager presets of the server ({"folder", "name"}), and the preset that the
    # collector uses now. The collector sends them with each ping. "Enviar al servidor" lists them.
    presets = models.JSONField(default=list, blank=True)
    preset = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.championship})"


def collector_path(instance, filename):
    return f"collector/{instance.token_id}/{instance.sha256[:16]}-{filename}"


class CollectorFile(models.Model):
    """A raw file from a collector. The app finds the round. An admin still applies the import."""

    class Kind(models.TextChoices):
        RESULT = "result", _("Result file")
        PENALTY_LOG = "penalty_log", _("Real Penalty log")

    class State(models.TextChoices):
        ASSIGNED = "assigned", _("Assigned to a round")
        UNMATCHED = "unmatched", _("No round found")
        REPLACED = "replaced", _("Replaced by a newer copy")
        FAILED = "failed", _("Not readable")

    token = models.ForeignKey(CollectorToken, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64)
    file = models.FileField(upload_to=collector_path)
    session_type = models.CharField(max_length=12, blank=True)
    track = models.CharField(max_length=100, blank=True)
    session_time = models.DateTimeField(null=True, blank=True)
    round = models.ForeignKey(
        Round, null=True, blank=True, on_delete=models.SET_NULL, related_name="collector_files"
    )
    status = models.CharField(max_length=10, choices=State.choices)
    error = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(fields=["token", "sha256"], name="unique_collector_file")
        ]

    def __str__(self):
        return self.filename


class CollectorEvent(models.Model):
    """One event from the UDP plugin connection. The run and the number make it unique, so a
    batch that comes again adds nothing."""

    token = models.ForeignKey(CollectorToken, on_delete=models.CASCADE, related_name="events")
    run_id = models.CharField(max_length=40)
    seq = models.PositiveIntegerField()
    kind = models.CharField(max_length=30)
    occurred_at = models.DateTimeField()
    data = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["token", "run_id", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["token", "run_id", "seq"], name="unique_event")
        ]

    def __str__(self):
        return f"{self.kind} {self.run_id}:{self.seq}"


class IncidentReview(models.Model):
    """A steward decision about one incident. The key is the first event of the incident."""

    class Outcome(models.TextChoices):
        OPEN = "open", _("Open")
        NO_ACTION = "no_action", _("No further action")
        RACING_INCIDENT = "racing_incident", _("Racing incident")
        PENALTY = "penalty", _("Penalty given")

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="incident_reviews")
    incident_key = models.BigIntegerField()
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.OPEN)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["round", "incident_key"], name="unique_incident_review")
        ]

    def __str__(self):
        return f"Review of incident {self.incident_key}"


class ServerPush(models.Model):
    """One "Enviar al servidor" of a round: the entry list, the handicaps, the conditions, and
    the Paddock script, for the server collector to write into the server preset (phase 4 of
    docs/plans/ac-integration.md)."""

    class State(models.TextChoices):
        PENDING = "pending", _("Waits for the collector")
        WAITING = "waiting", _("Waits for the server to stop")
        DONE = "done", _("Written")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Replaced by a newer one")

    championship = models.ForeignKey(
        Championship, on_delete=models.CASCADE, related_name="server_pushes"
    )
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="server_pushes")
    content = models.JSONField()
    status = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    error = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    collector = models.ForeignKey(
        CollectorToken, null=True, blank=True, on_delete=models.SET_NULL, related_name="pushes"
    )
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Push of {self.round} ({self.status})"
