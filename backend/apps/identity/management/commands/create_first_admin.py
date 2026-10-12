import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Make the first admin account. The password comes from the environment variable "
        "FIRST_ADMIN_PASSWORD, or from a prompt."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--if-missing",
            action="store_true",
            help="Do nothing when a user with this username exists.",
        )

    def handle(self, *args, username, email, if_missing, **options):
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            if if_missing:
                self.stdout.write(f"The user {username} exists. No change.")
                return
            raise CommandError(f"The user {username} exists.")

        password = os.environ.get("FIRST_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        user = User(username=username, email=email, is_staff=True, is_superuser=True)
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Made the admin account {username}."))
