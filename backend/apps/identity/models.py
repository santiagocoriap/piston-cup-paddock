from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Language(models.TextChoices):
        SPANISH = "es", _("Spanish")
        ENGLISH = "en", _("English")

    language = models.CharField(max_length=2, choices=Language.choices, default=Language.SPANISH)
