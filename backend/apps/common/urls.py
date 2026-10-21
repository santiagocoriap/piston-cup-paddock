"""The public address of the app, for links that leave the browser: the Paddock script in the
game of each driver, the collector, and the calendar feeds."""

from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def public_url(request: HttpRequest) -> str:
    """PUBLIC_URL when it is set. Else the address of the request, which is the address that the
    admin sees in the browser."""
    return settings.PUBLIC_URL or request.build_absolute_uri("/").rstrip("/")


def is_local(url: str) -> bool:
    """True for an address that only the same computer can open. The game of another driver
    cannot reach it."""
    return (urlparse(url).hostname or "") in LOCAL_HOSTS
