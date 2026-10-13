from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Car, TrackLayout
from apps.competition.models import Championship
from apps.identity.models import DriverProfile


class ManualRecord(models.Model):
    """A historical record that an admin enters by hand, for laps from before the app. It needs
    a source. Until an admin verifies it, the page shows it as unverified."""

    class Category(models.TextChoices):
        QUALIFYING = "qualifying", _("Qualifying")
        RACE = "race", _("Race")

    championship = models.ForeignKey(
        Championship, on_delete=models.CASCADE, related_name="manual_records"
    )
    layout = models.ForeignKey(TrackLayout, on_delete=models.PROTECT, related_name="+")
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name="+")
    category = models.CharField(max_length=10, choices=Category.choices)
    lap_time_ms = models.PositiveIntegerField()
    driver = models.ForeignKey(
        DriverProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    driver_name = models.CharField(max_length=100)
    date = models.DateField()
    source = models.CharField(max_length=300)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["layout", "category", "lap_time_ms"]

    def __str__(self):
        return f"{self.driver_name} {self.lap_time_ms} ms on {self.layout}"
