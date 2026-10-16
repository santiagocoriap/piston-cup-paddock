from django.conf import settings
from django.db import models

from apps.competition.models import Championship


class AuditEntry(models.Model):
    """One change. The frontend turns the action and the params into a sentence.

    Never put a password, a credential, or raw telemetry in params or changes.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    actor_name = models.CharField(max_length=150)  # Kept when the account goes away.
    action = models.CharField(max_length=50)
    championship = models.ForeignKey(
        Championship, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit"
    )
    # The name when the entry was written. It stays after the championship is deleted.
    championship_name = models.CharField(max_length=100, blank=True)
    target_type = models.CharField(max_length=30)
    target_id = models.PositiveBigIntegerField()
    params = models.JSONField(default=dict)
    changes = models.JSONField(default=list)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.actor_name} {self.action} {self.target_type}:{self.target_id}"
