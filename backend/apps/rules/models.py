from django.conf import settings
from django.db import models

from apps.competition.models import Season

from .handicaps import LEAGUE_BALLAST_STEPS, LEAGUE_RESTRICTOR_STEPS, HandicapRules
from .scoring import LEAGUE_POINTS, PointsRules


class RulesVersion(models.Model):
    """The sporting rules of a season. A change makes a new version, so old results keep theirs."""

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rules_versions")
    number = models.PositiveSmallIntegerField()
    points_by_position = models.JSONField()
    pole_bonus = models.PositiveSmallIntegerField(default=0)
    fastest_lap_bonus = models.PositiveSmallIntegerField(default=0)
    ballast_steps = models.JSONField(default=list)
    restrictor_steps = models.JSONField(default=list)
    ballast_cap = models.PositiveSmallIntegerField(default=45)
    restrictor_cap = models.PositiveSmallIntegerField(default=5)
    ballast_reduction = models.PositiveSmallIntegerField(default=3)
    restrictor_reduction = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["season", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "number"], name="unique_rules_version")
        ]

    def __str__(self):
        return f"{self.season} rules v{self.number}"

    @classmethod
    def current_for(cls, season: Season) -> "RulesVersion":
        """The newest version. A season without rules gets the league defaults as version 1."""
        latest = cls.objects.filter(season=season).order_by("-number").first()
        if latest:
            return latest
        return cls.objects.create(
            season=season,
            number=1,
            points_by_position=list(LEAGUE_POINTS),
            ballast_steps=list(LEAGUE_BALLAST_STEPS),
            restrictor_steps=list(LEAGUE_RESTRICTOR_STEPS),
        )

    def as_points_rules(self) -> PointsRules:
        return PointsRules(
            points_by_position=tuple(self.points_by_position),
            pole_bonus=self.pole_bonus,
            fastest_lap_bonus=self.fastest_lap_bonus,
        )

    def as_handicap_rules(self) -> HandicapRules:
        return HandicapRules(
            ballast_steps=tuple(self.ballast_steps),
            restrictor_steps=tuple(self.restrictor_steps),
            ballast_cap=self.ballast_cap,
            restrictor_cap=self.restrictor_cap,
            ballast_reduction=self.ballast_reduction,
            restrictor_reduction=self.restrictor_reduction,
        )
