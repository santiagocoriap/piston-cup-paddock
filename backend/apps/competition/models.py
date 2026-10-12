from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Car, TrackLayout
from apps.identity.models import DriverProfile


class League(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Championship(models.Model):
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="championships")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["league", "name"], name="unique_championship_name")
        ]

    def __str__(self):
        return self.name


class ChampionshipMember(models.Model):
    """Gives a user a role in one championship. Roles never reach other championships."""

    class Role(models.TextChoices):
        ADMIN = "admin", _("Admin")
        DRIVER = "driver", _("Driver")

    championship = models.ForeignKey(Championship, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="championship_roles"
    )
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["championship", "user"], name="unique_member")
        ]

    def __str__(self):
        return f"{self.user} - {self.championship} ({self.role})"


class Season(models.Model):
    championship = models.ForeignKey(Championship, on_delete=models.PROTECT, related_name="seasons")
    name = models.CharField(max_length=100)
    planned_round_count = models.PositiveSmallIntegerField()
    protest_window_minutes = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["championship", "name"], name="unique_season_name")
        ]

    def __str__(self):
        return self.name


class SeasonEntry(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="entries")
    driver = models.ForeignKey(DriverProfile, on_delete=models.PROTECT, related_name="entries")
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name="entries")
    number = models.PositiveSmallIntegerField()
    team = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "driver"], name="unique_driver_per_season"),
            models.UniqueConstraint(fields=["season", "number"], name="unique_number_per_season"),
        ]

    def __str__(self):
        return f"#{self.number} {self.driver}"


class Round(models.Model):
    class Origin(models.TextChoices):
        FIXED = "fixed", _("Fixed")
        VOTED = "voted", _("Voted")
        MANUAL = "manual", _("Manual")

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rounds")
    number = models.PositiveSmallIntegerField()
    track_layout = models.ForeignKey(TrackLayout, on_delete=models.PROTECT, related_name="rounds")
    scheduled_at = models.DateTimeField()
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.MANUAL)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "number"], name="unique_round_number")
        ]

    def __str__(self):
        return f"Round {self.number} - {self.track_layout}"


class Session(models.Model):
    """Practice, qualifying, or race of one round.

    Only race sessions give points and count restarts.
    """

    class Kind(models.TextChoices):
        PRACTICE = "practice", _("Practice")
        QUALIFYING = "qualifying", _("Qualifying")
        RACE = "race", _("Race")

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="sessions")
    kind = models.CharField(max_length=12, choices=Kind.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["round", "kind"], name="unique_session_kind")
        ]

    def __str__(self):
        return f"{self.round} {self.kind}"


class Attempt(models.Model):
    """One actual start of a session. A restart ends one attempt and starts the next."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        COMPLETED = "completed", _("Completed")
        ABANDONED = "abandoned", _("Abandoned")
        ACCEPTED = "accepted", _("Accepted")
        INVALIDATED = "invalidated", _("Invalidated")

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["session", "number"], name="unique_attempt_number")
        ]

    def __str__(self):
        return f"{self.session} attempt {self.number}"
