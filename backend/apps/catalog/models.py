from django.conf import settings
from django.db import models


def layout_image_path(layout, filename):
    folder = layout.key or "default"
    return f"catalog/tracks/{layout.track.key}/{folder}/{filename}"


def car_image_path(car, filename):
    return f"catalog/cars/{car.key}/{filename}"


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
    # The league guidance for a first-lap restart on this layout, for the briefing.
    restart_guidance = models.TextField(blank=True)
    first_lap_cutoff = models.CharField(max_length=200, blank=True)
    # The number of pit boxes. A track ballot refuses a layout with fewer boxes than drivers.
    pit_boxes = models.PositiveSmallIntegerField(null=True, blank=True)
    # From the game files (ui/<layout>/): the track map and a picture. See game_images.py.
    outline = models.FileField(upload_to=layout_image_path, blank=True)
    preview = models.FileField(upload_to=layout_image_path, blank=True)
    length_m = models.PositiveIntegerField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["track__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["track", "key"], name="unique_layout_per_track")
        ]

    def __str__(self):
        return f"{self.track.name} - {self.name}"

    def image_url(self, kind: str) -> str | None:
        """The API path of the outline or preview picture, or None without a picture."""
        return f"/api/catalog/layouts/{self.id}/images/{kind}" if getattr(self, kind) else None


class Car(models.Model):
    """A car folder in the AC content, for example trr_lmdh_acura_arx-06."""

    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    # From the game files: a skin preview, the brand badge, and the text of ui_car.json.
    preview = models.FileField(upload_to=car_image_path, blank=True)
    badge = models.FileField(upload_to=car_image_path, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    author = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def image_url(self, kind: str) -> str | None:
        """The API path of the preview or badge picture, or None without a picture."""
        return f"/api/catalog/cars/{self.id}/images/{kind}" if getattr(self, kind) else None


class CarClass(models.Model):
    """A group of cars, for example GT3 or LMDh. Ballots, entries, and records use it."""

    name = models.CharField(max_length=60, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def image_url(self, kind: str) -> str | None:
        """The API path of the preview or badge picture, or None without a picture."""
        return f"/api/catalog/cars/{self.id}/images/{kind}" if getattr(self, kind) else None


class CarClassMembership(models.Model):
    """A car is in a class from valid_from until valid_to. An open row has no valid_to. A
    change closes the old row and opens a new one, so the history stays."""

    car_class = models.ForeignKey(CarClass, on_delete=models.CASCADE, related_name="memberships")
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="class_memberships")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["car_class", "car", "valid_from"]

    def __str__(self):
        return f"{self.car} in {self.car_class}"


def classes_of(car_id: int, day) -> list[int]:
    """The classes of a car on a day."""
    rows = CarClassMembership.objects.filter(car_id=car_id, valid_from__lte=day).filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=day)
    )
    return list(rows.values_list("car_class_id", flat=True))
