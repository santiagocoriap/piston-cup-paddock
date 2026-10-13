from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.competition.models import Round, SeasonEntry


class Attendance(models.Model):
    """A driver says if they come to a round."""

    class Answer(models.TextChoices):
        YES = "yes", _("Yes")
        MAYBE = "maybe", _("Maybe")
        NO = "no", _("No")

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="attendance")
    entry = models.ForeignKey(SeasonEntry, on_delete=models.CASCADE, related_name="attendance")
    answer = models.CharField(max_length=5, choices=Answer.choices)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["round", "entry"], name="unique_attendance")]

    def __str__(self):
        return f"{self.entry} {self.answer} for {self.round}"


class Notification(models.Model):
    """A message in the app for one user. The page writes the text from the kind and params."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=40)
    params = models.JSONField(default=dict)
    link = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.kind} for {self.user}"


class CalendarFeed(models.Model):
    """The secret address of the calendar feed of one user. A phone calendar reads it without
    a session, so the token is in the address. It shows only round dates."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed"
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Calendar feed of {self.user}"
