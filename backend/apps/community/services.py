"""Attendance, notifications, and calendar files."""

import secrets
from datetime import UTC, timedelta

from django.utils import timezone

from apps.competition.models import ChampionshipMember, Round, Season

from .models import CalendarFeed, Notification

RACE_LENGTH = timedelta(hours=2)  # The calendar event length of one round.


# Notifications


def notify(user_ids, kind: str, params: dict, link: str = "") -> int:
    """Add one notification for each user. Gives the count."""
    ids = {uid for uid in user_ids if uid}
    Notification.objects.bulk_create(
        Notification(user_id=uid, kind=kind, params=params, link=link) for uid in ids
    )
    return len(ids)


def season_user_ids(season: Season) -> set[int]:
    """The members of the championship and the users of the drivers of the season."""
    members = ChampionshipMember.objects.filter(championship=season.championship).values_list(
        "user_id", flat=True
    )
    drivers = season.entries.filter(driver__user__isnull=False).values_list(
        "driver__user_id", flat=True
    )
    return set(members) | set(drivers)


def staff_user_ids(season: Season, capability: str) -> set[int]:
    """The users with a capability in the championship, without league admins of other
    championships."""
    from apps.competition.permissions import can

    members = ChampionshipMember.objects.filter(championship=season.championship).select_related(
        "user"
    )
    return {m.user_id for m in members if can(m.user, season.championship, capability)}


def round_params(round_: Round) -> dict:
    return {
        "championship": round_.season.championship.name,
        "season": round_.season.name,
        "number": round_.number,
        "track": round_.track_layout.track.name,
    }


# Calendar


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(value) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def ics(rounds, base_url: str, name: str) -> str:
    """An iCalendar file with one event for each round that has a date."""
    stamp = _ics_time(timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Piston Cup Paddock//ES",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_text(name)}",
    ]
    for round_ in rounds:
        if round_.scheduled_at is None:
            continue
        season = round_.season
        layout = round_.track_layout
        summary = f"{season.championship.name} R{round_.number} · {layout.track.name}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:round-{round_.id}@piston-cup-paddock",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_time(round_.scheduled_at)}",
            f"DTEND:{_ics_time(round_.scheduled_at + RACE_LENGTH)}",
            f"SUMMARY:{_ics_text(summary)}",
            f"DESCRIPTION:{_ics_text(f'{season.name} · {layout.name}')}",
            f"URL:{base_url}/rounds/{round_.id}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def feed_for(user) -> CalendarFeed:
    feed = CalendarFeed.objects.filter(user=user).first()
    return feed or CalendarFeed.objects.create(user=user, token=secrets.token_urlsafe(32))


def new_feed(user) -> CalendarFeed:
    """A new address. The old address stops working."""
    CalendarFeed.objects.filter(user=user).delete()
    return CalendarFeed.objects.create(user=user, token=secrets.token_urlsafe(32))
