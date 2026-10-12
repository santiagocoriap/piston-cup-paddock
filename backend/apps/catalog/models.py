from django.db import models


class Track(models.Model):
    """A track folder in the AC content, for example ks_highlands."""

    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TrackLayout(models.Model):
    """One exact layout of a track. An empty key is the default layout."""

    track = models.ForeignKey(Track, on_delete=models.PROTECT, related_name="layouts")
    key = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["track__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["track", "key"], name="unique_layout_per_track")
        ]

    def __str__(self):
        return f"{self.track.name} - {self.name}"


class Car(models.Model):
    """A car folder in the AC content, for example trr_lmdh_acura_arx-06."""

    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
