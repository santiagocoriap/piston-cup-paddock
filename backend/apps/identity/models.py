from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Language(models.TextChoices):
        SPANISH = "es", _("Spanish")
        ENGLISH = "en", _("English")

    language = models.CharField(max_length=2, choices=Language.choices, default=Language.SPANISH)
    # An IANA timezone, for example "Europe/Madrid". Empty means the timezone of the browser.
    timezone = models.CharField(max_length=64, blank=True)


steam_guid_validator = RegexValidator(r"^\d{17}$", _("A Steam GUID has 17 digits."))


class DriverProfile(models.Model):
    """A driver in the league. A profile can exist before its owner has an account."""

    display_name = models.CharField(max_length=100)
    steam_guid = models.CharField(
        max_length=17, unique=True, null=True, blank=True, validators=[steam_guid_validator]
    )
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_profile"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name
