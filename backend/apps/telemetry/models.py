from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round
from apps.identity.models import DriverProfile


class DriverKey(models.Model):
    """The key of the driver collector of one driver. The app keeps only a hash."""

    driver = models.OneToOneField(
        DriverProfile, on_delete=models.CASCADE, related_name="telemetry_key"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Telemetry key of {self.driver}"


class Access(models.TextChoices):
    NONE = "none", _("Nothing")
    LAPS = "laps", _("Lap times and speed")
    FULL = "full", _("Everything, with inputs")


class TelemetrySharing(models.Model):
    """Who sees the telemetry of a driver. Other drivers never get the inputs."""

    driver = models.OneToOneField(
        DriverProfile, on_delete=models.CASCADE, related_name="telemetry_sharing"
    )
    teammates = models.CharField(max_length=4, choices=Access.choices, default=Access.LAPS)
    drivers = models.CharField(max_length=4, choices=Access.choices, default=Access.NONE)
    admins = models.CharField(max_length=4, choices=Access.choices, default=Access.LAPS)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sharing of {self.driver}"


def telemetry_path(instance, filename):
    return f"telemetry/driver-{instance.driver_id}/{instance.sha256[:16]}.json"


class TelemetryLap(models.Model):
    """One lap from the driver collector. The samples are in a JSON file."""

    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name="laps")
    round = models.ForeignKey(
        Round, null=True, blank=True, on_delete=models.SET_NULL, related_name="telemetry_laps"
    )
    sha256 = models.CharField(max_length=64)
    session_type = models.CharField(max_length=12, blank=True)
    track = models.CharField(max_length=100)
    car = models.CharField(max_length=100)
    lap_number = models.PositiveSmallIntegerField()
    lap_time_ms = models.PositiveIntegerField()
    valid = models.BooleanField(default=True)
    recorded_at = models.DateTimeField()
    sample_hz = models.PositiveSmallIntegerField()
    samples = models.FileField(upload_to=telemetry_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["recorded_at", "lap_number"]
        constraints = [
            models.UniqueConstraint(fields=["driver", "sha256"], name="unique_telemetry_lap")
        ]

    def __str__(self):
        return f"{self.driver} lap {self.lap_number}"
