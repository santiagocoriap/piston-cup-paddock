from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round, SeasonEntry


class HandicapAdjustment(models.Model):
    """An admin sets the ballast and restrictor that one driver carries into one round."""

    class Mode(models.TextChoices):
        TEMPORARY = "temporary", _("Only this round")
        PERSISTENT = "persistent", _("This round and the next rounds")

    entry = models.ForeignKey(SeasonEntry, on_delete=models.CASCADE, related_name="adjustments")
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="adjustments")
    ballast_kg = models.PositiveSmallIntegerField()
    restrictor_pct = models.PositiveSmallIntegerField()
    mode = models.CharField(max_length=10, choices=Mode.choices)
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["entry", "round"], name="unique_adjustment")]

    def __str__(self):
        return f"{self.entry} R{self.round.number}: {self.ballast_kg} kg {self.restrictor_pct} %"


class UsedHandicap(models.Model):
    """The values that a driver carried in a race. The app saves them with the first result of
    the round. A later correction changes the next rounds, but never these values."""

    entry = models.ForeignKey(SeasonEntry, on_delete=models.CASCADE, related_name="used_handicaps")
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="used_handicaps")
    ballast_kg = models.PositiveSmallIntegerField()
    restrictor_pct = models.PositiveSmallIntegerField()
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entry", "round"], name="unique_used_handicap")
        ]

    def __str__(self):
        return f"{self.entry} R{self.round.number}: {self.ballast_kg} kg {self.restrictor_pct} %"
