from django.conf import settings
from django.db import models


class BackupRun(models.Model):
    """One backup, from the page or from the `backup` command. The health card shows the last."""

    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        FAILED = "failed"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    file_name = models.CharField(max_length=200, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    rows = models.IntegerField(null=True, blank=True)
    files = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self):
        return f"Backup {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
