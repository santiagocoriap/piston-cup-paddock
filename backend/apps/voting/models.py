from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import TrackLayout
from apps.competition.models import Season


class Ballot(models.Model):
    """A vote of a season on tracks or on car classes."""

    class Kind(models.TextChoices):
        TRACK = "track", _("Tracks")
        CAR_CLASS = "car_class", _("Car classes")

    class State(models.TextChoices):
        DRAFT = "draft", _("Draft")
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")  # Waiting for a decision: a tie, or too few votes.
        DECIDED = "decided", _("Decided")

    class Method(models.TextChoices):
        SINGLE = "single", _("One choice")
        MULTIPLE = "multiple", _("Up to the selection limit")

    class ChoiceVisibility(models.TextChoices):
        VISIBLE = "visible", _("Drivers see who chose what")
        HIDDEN = "hidden", _("Hidden from other drivers")

    class TotalsVisibility(models.TextChoices):
        LIVE = "live", _("Running totals")
        AFTER_CLOSE = "after_close", _("After the close")
        HIDDEN = "hidden", _("Only admins")

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="ballots")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=10, choices=State.choices, default=State.DRAFT)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.MULTIPLE)
    selection_limit = models.PositiveSmallIntegerField(default=1)
    slots = models.PositiveSmallIntegerField(default=1)  # The number of options that win.
    choice_visibility = models.CharField(
        max_length=10, choices=ChoiceVisibility.choices, default=ChoiceVisibility.HIDDEN
    )
    totals_visibility = models.CharField(
        max_length=12, choices=TotalsVisibility.choices, default=TotalsVisibility.AFTER_CLOSE
    )
    allow_vote_changes = models.BooleanField(default=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    # The worker opens a draft at opens_at and closes an open ballot at closes_at.
    opens_at = models.DateTimeField(null=True, blank=True)
    # A reminder to the voters with no vote, this many hours before the close. 0: no reminder.
    remind_hours_before = models.PositiveSmallIntegerField(default=24)
    reminded_at = models.DateTimeField(null=True, blank=True)
    # The share of voters who must vote. 0: no minimum.
    min_participation_pct = models.PositiveSmallIntegerField(default=0)
    # "admin": with too few votes the ballot closes with no winner, and an admin decides.
    # "count": the votes count anyway.
    low_participation_action = models.CharField(max_length=5, default="admin")
    low_participation = models.BooleanField(default=False)
    # True: everybody sees who voted (not what they chose, unless choices are visible).
    show_voter_names = models.BooleanField(default=False)
    # Tracks that this ballot does not accept, for example a venue of the last season.
    excluded_track_ids = models.JSONField(default=list)
    # Eligibility. The app freezes the voter list when the ballot opens.
    eligible_roles = models.JSONField(default=list)  # Championship roles, for example ["driver"].
    prior_season = models.ForeignKey(
        Season, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    min_prior_starts = models.PositiveSmallIntegerField(default=0)
    # Vote power exceptions: {user ID: power}. Everybody else has power 1.
    power_overrides = models.JSONField(default=dict)
    # Runoffs
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="runoffs"
    )
    max_runoffs = models.PositiveSmallIntegerField(null=True, blank=True)  # None means no limit.
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_early = models.BooleanField(default=False)
    close_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def runoff_depth(self) -> int:
        depth, ballot = 0, self
        while ballot.parent_id:
            depth += 1
            ballot = ballot.parent
        return depth


class BallotOption(models.Model):
    class Source(models.TextChoices):
        VOTE = "vote", _("Votes")
        RUNOFF = "runoff", _("Runoff")
        ADMIN = "admin", _("Admin decision")

    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=150)
    track_layout = models.ForeignKey(
        TrackLayout, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    selected = models.BooleanField(default=False)
    selected_by = models.CharField(max_length=10, choices=Source.choices, blank=True)
    origin = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )  # The same option in the parent ballot of a runoff.

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(fields=["ballot", "label"], name="unique_option_label")
        ]

    def __str__(self):
        return self.label


class BallotVoter(models.Model):
    """A voter in the frozen list, with the vote power."""

    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name="voters")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    power = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ballot", "user"], name="unique_voter")]

    def __str__(self):
        return f"{self.user} x{self.power}"


class Vote(models.Model):
    voter = models.ForeignKey(BallotVoter, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(BallotOption, on_delete=models.CASCADE, related_name="votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["voter", "option"], name="unique_vote")]

    def __str__(self):
        return f"{self.voter} → {self.option}"
