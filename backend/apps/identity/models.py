from django.conf import settings
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


class LoginFailure(models.Model):
    """One wrong password. The login limit counts these rows. The password is never stored."""

    username = models.CharField(max_length=150, db_index=True)
    ip = models.CharField(max_length=45, blank=True, db_index=True)
    failed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.username} from {self.ip} at {self.failed_at:%Y-%m-%d %H:%M}"


class AccountLink(models.Model):
    """A one-time link to set a password. The database keeps only the SHA-256 hash of the token."""

    class Purpose(models.TextChoices):
        INVITE = "invite", _("Invite")
        RESET = "reset", _("Password reset")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_links")
    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.purpose} link for {self.user}"


class CareerAdjustment(models.Model):
    """An admin change to the career points of a driver. The race history stays as it is.

    "adjust" adds points (negative to take away). "reset" starts the career count again from
    zero: raw_points keeps the official points of the driver at that moment."""

    class Kind(models.TextChoices):
        ADJUST = "adjust", "Adjust"
        RESET = "reset", "Reset"

    driver = models.ForeignKey(
        DriverProfile, on_delete=models.CASCADE, related_name="career_adjustments"
    )
    kind = models.CharField(max_length=6, choices=Kind.choices)
    points = models.IntegerField(default=0)
    raw_points = models.IntegerField(default=0)
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.kind} {self.points} for {self.driver}"
