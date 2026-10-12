"""Limit wrong password attempts. The counts live in the database, so every gunicorn worker
sees the same counts.

- 5 wrong passwords for one username in 15 minutes block that username.
- 20 wrong passwords from one IP address in 15 minutes block that IP address.
- A block lasts until the oldest of those failures is older than 15 minutes.
- A correct login clears the failures of that username.
"""

from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

from .models import LoginFailure

WINDOW = timedelta(minutes=15)
USERNAME_LIMIT = 5
IP_LIMIT = 20


def client_ip(request: HttpRequest) -> str:
    """The address of the client.

    Behind a proxy (Coolify uses Traefik), REMOTE_ADDR is the proxy. Each trusted proxy adds the
    address that it sees to the right end of X-Forwarded-For. With TRUSTED_PROXY_COUNT = N, the
    app takes the Nth address from the right. A client can put any text in the header, but only
    at the left end, so it cannot change the address that the app takes.
    """
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies > 0:
        forwarded = [
            part.strip()
            for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
            if part.strip()
        ]
        if len(forwarded) >= proxies:
            return forwarded[-proxies]
    return request.META.get("REMOTE_ADDR", "")


def is_blocked(username: str, ip: str) -> bool:
    since = timezone.now() - WINDOW
    recent = LoginFailure.objects.filter(failed_at__gte=since)
    if recent.filter(username=username.lower()).count() >= USERNAME_LIMIT:
        return True
    return bool(ip) and recent.filter(ip=ip).count() >= IP_LIMIT


def record_failure(username: str, ip: str) -> None:
    LoginFailure.objects.create(username=username.lower()[:150], ip=ip)
    # Keep the table small. Old rows have no use.
    LoginFailure.objects.filter(failed_at__lt=timezone.now() - timedelta(days=1)).delete()


def clear_failures(username: str) -> None:
    LoginFailure.objects.filter(username=username.lower()).delete()
