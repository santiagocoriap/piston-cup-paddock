from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Car, TrackLayout
from apps.identity.models import DriverProfile


class League(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # The timezone of the race server. The app shows race times in it next to the driver time.
    timezone = models.CharField(max_length=64, default="America/Argentina/Buenos_Aires")

    def __str__(self):
        return self.name


class Team(models.Model):
    """A team of a league. The entry form lists them, so a team name has one spelling."""

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["league", "name"], name="unique_team")]

    def __str__(self):
        return self.name


class Championship(models.Model):
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="championships")
    name = models.CharField(max_length=100)
    # Write a provisional AI report when a race file is applied, before the approval.
    provisional_reports = models.BooleanField(default=False)
    # Apply a clean result file from the server collector with no admin click. The result
    # stays provisional until an admin approves it. See docs/adr/0002-collector-automation.md.
    auto_publish_results = models.BooleanField(default=True)
    # Free slots after the league drivers in the server entry list, so a driver can change to an
    # extra car. "Enviar al servidor" sends this number. An admin can change it for one push.
    open_slots = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["league", "name"], name="unique_championship_name")
        ]

    def __str__(self):
        return self.name


class ChampionshipRole(models.Model):
    """A custom role of one championship with selected capabilities. The capabilities are in
    apps.competition.permissions.CAPABILITIES."""

    championship = models.ForeignKey(Championship, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=60)
    capabilities = models.JSONField(default=list)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["championship", "name"], name="unique_role_name")
        ]

    def __str__(self):
        return f"{self.championship} - {self.name}"


class ChampionshipMember(models.Model):
    """Gives a user a role in one championship. Roles never reach other championships."""

    class Role(models.TextChoices):
        ADMIN = "admin", _("Admin")
        DRIVER = "driver", _("Driver")
        STEWARD = "steward", _("Steward")
        CUSTOM = "custom", _("Custom role")

    championship = models.ForeignKey(Championship, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="championship_roles"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    # Only for the custom role. The role must belong to the same championship.
    custom_role = models.ForeignKey(
        ChampionshipRole, null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )

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
    # By default a fixed layout cannot also be a voting candidate.
    allow_repeat_layouts = models.BooleanField(default=False)
    # Free join: a driver enters the season alone. Off: the driver asks, and an admin decides.
    free_join = models.BooleanField(default=False)
    # The car classes of the season. An entry can only use a car of these classes. Empty: any
    # car. A decided car class vote fills it.
    car_classes = models.ManyToManyField("catalog.CarClass", blank=True, related_name="seasons")
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
    # Empty until the driver or an admin chooses a car, for example before the car class vote.
    car = models.ForeignKey(
        Car, null=True, blank=True, on_delete=models.PROTECT, related_name="entries"
    )
    number = models.PositiveSmallIntegerField()
    team = models.CharField(max_length=100, blank=True)
    # The skin that the driver chose for the car. Empty: the server picks one. The skin must be
    # a skin of the car of the entry (the API checks it).
    skin = models.ForeignKey(
        "catalog.CarSkin", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "driver"], name="unique_driver_per_season"),
            models.UniqueConstraint(fields=["season", "number"], name="unique_number_per_season"),
        ]

    def __str__(self):
        return f"#{self.number} {self.driver}"

    @property
    def car_name(self) -> str:
        return self.car.name if self.car_id else ""


class JoinRequest(models.Model):
    """A driver asks to enter a season that has no free join. An admin approves or declines."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        DECLINED = "declined", _("Declined")

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="join_requests")
    driver = models.ForeignKey(
        DriverProfile, on_delete=models.CASCADE, related_name="join_requests"
    )
    car = models.ForeignKey(Car, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    number = models.PositiveSmallIntegerField()
    team = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["season", "driver"],
                condition=models.Q(status="pending"),
                name="one_pending_request_per_driver",
            )
        ]

    def __str__(self):
        return f"{self.driver} -> {self.season} ({self.status})"


class Round(models.Model):
    class Origin(models.TextChoices):
        FIXED = "fixed", _("Fixed")
        VOTED = "voted", _("Voted")
        MANUAL = "manual", _("Manual")

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rounds")
    number = models.PositiveSmallIntegerField()
    track_layout = models.ForeignKey(TrackLayout, on_delete=models.PROTECT, related_name="rounds")
    # A voted or fixed round can wait for its date. The admin sets it in the calendar.
    scheduled_at = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.MANUAL)
    # What the admin announces before the race: time of day, weather, temperatures, grip, notes.
    # The observed conditions can differ and never replace these values.
    announced_conditions = models.JSONField(default=dict, blank=True)
    # A cancelled round gives no points and does not change handicaps (docs/LEAGUE_RULES.md).
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

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


class RoundTrackChange(models.Model):
    """A replaced track of a calendar round. The old track and the reason stay here."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="track_changes")
    old_layout = models.ForeignKey(TrackLayout, on_delete=models.PROTECT, related_name="+")
    new_layout = models.ForeignKey(TrackLayout, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "id"]

    def __str__(self):
        return f"{self.round}: {self.old_layout} -> {self.new_layout}"


class ConditionsPool(models.Model):
    """The choices for the conditions draw of a season. An empty list leaves that value out."""

    season = models.OneToOneField(Season, on_delete=models.CASCADE, related_name="conditions_pool")
    weather = models.JSONField(default=list)
    time_of_day = models.JSONField(default=list)
    grip = models.JSONField(default=list)
    air_temp_min = models.SmallIntegerField(null=True, blank=True)
    air_temp_max = models.SmallIntegerField(null=True, blank=True)
    track_temp_min = models.SmallIntegerField(null=True, blank=True)
    track_temp_max = models.SmallIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Conditions pool of {self.season}"


class ConditionsDraw(models.Model):
    """One draw of the conditions of a round. A new draw keeps the earlier ones here."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="conditions_draws")
    values = models.JSONField()
    reason = models.TextField(blank=True)  # Required for a new draw after the first.
    drawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    drawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["drawn_at", "id"]

    def __str__(self):
        return f"Draw for {self.round}"
