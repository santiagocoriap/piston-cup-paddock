from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Championship, Round
from apps.identity.models import DriverProfile


class Access(models.TextChoices):
    NONE = "none", _("Nothing")
    LAPS = "laps", _("Lap times and speed")
    FULL = "full", _("Everything, with inputs")


class TelemetrySharing(models.Model):
    """Who sees the telemetry of a driver. Everybody sees everything at first, so the league can
    compare laps with no setup. The driver can choose a lower level."""

    driver = models.OneToOneField(
        DriverProfile, on_delete=models.CASCADE, related_name="telemetry_sharing"
    )
    teammates = models.CharField(max_length=4, choices=Access.choices, default=Access.FULL)
    drivers = models.CharField(max_length=4, choices=Access.choices, default=Access.FULL)
    admins = models.CharField(max_length=4, choices=Access.choices, default=Access.FULL)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sharing of {self.driver}"


def telemetry_path(instance, filename):
    return f"telemetry/driver-{instance.driver_id}/{instance.sha256[:16]}.json"


class TelemetryLap(models.Model):
    """One lap from the Paddock script. The samples are in a JSON file. Older laps came from the
    driver collector, which is removed."""

    class Source(models.TextChoices):
        COLLECTOR = "collector", _("Driver collector")
        SCRIPT = "script", _("Paddock script")

    class Match(models.TextChoices):
        PENDING = "pending", _("Waits for the server data")
        LEAGUE = "league", _("A league session")

    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name="laps")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SCRIPT)
    # Only for a lap of the script: the championship of the race code, the match state, the
    # start of the server session, and the race start number.
    championship = models.ForeignKey(
        Championship, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    match = models.CharField(max_length=8, choices=Match.choices, blank=True)
    server_session_at = models.DateTimeField(null=True, blank=True)
    # The track cuts of the lap, from the server. None when no server saw the lap.
    cuts = models.PositiveSmallIntegerField(null=True, blank=True)
    attempt_number = models.PositiveSmallIntegerField(null=True, blank=True)
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


class ScriptCode(models.Model):
    """The race code of a championship. The server gives it to the Paddock script of each driver
    who joins, and the script sends it with each lap. A new code replaces the old one, which
    still works for a few hours, so the laps of a race in progress still count."""

    championship = models.ForeignKey(
        Championship, on_delete=models.CASCADE, related_name="script_codes"
    )
    code = models.CharField(max_length=40, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Script code of {self.championship}"


class EngineerNote(models.Model):
    """A short coaching note that the AI writes from the numbers of the race engineer. The app
    keeps it, so the same lap and reference never cost a second AI call."""

    class State(models.TextChoices):
        PENDING = "pending", _("Pending")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")

    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name="+")
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="engineer_notes")
    lap = models.ForeignKey(TelemetryLap, on_delete=models.CASCADE, related_name="+")
    # "own" for the best corners of the driver, or the ID of the reference lap.
    reference = models.CharField(max_length=20)
    language = models.CharField(max_length=5, choices=settings.LANGUAGES)
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
        ordering = ["-created_at"]

    def __str__(self):
        return f"Engineer note for {self.driver} lap {self.lap_id}"
