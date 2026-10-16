"""The search box in the header: championships, seasons, rounds, and drivers the user can see."""

from dataclasses import dataclass

from django.db.models import Q

from apps.competition.models import Round, Season
from apps.competition.permissions import is_league_admin, visible_championships
from apps.identity.models import DriverProfile

MIN_LENGTH = 2
PER_KIND = 5


@dataclass
class Hit:
    kind: str  # "championship", "season", "round", or "driver"
    label: str
    detail: str
    path: str
    number: int | None = None  # The round number, for a round.


def search(user, query: str) -> list[Hit]:
    query = query.strip()
    if len(query) < MIN_LENGTH:
        return []
    championships = visible_championships(user)
    hits: list[Hit] = []

    for championship in championships.filter(name__icontains=query).select_related("league")[
        :PER_KIND
    ]:
        hits.append(
            Hit(
                "championship",
                championship.name,
                championship.league.name,
                f"/championships/{championship.id}",
            )
        )

    seasons = (
        Season.objects.filter(championship__in=championships)
        .filter(Q(name__icontains=query) | Q(championship__name__icontains=query))
        .select_related("championship")[:PER_KIND]
    )
    for season in seasons:
        name = f"{season.championship.name} {season.name}"
        hits.append(Hit("season", name, season.championship.name, f"/seasons/{season.id}"))

    rounds = (
        Round.objects.filter(season__championship__in=championships, cancelled_at__isnull=True)
        .filter(
            Q(track_layout__track__name__icontains=query) | Q(track_layout__name__icontains=query)
        )
        .select_related("season__championship", "track_layout__track")
        .order_by("-season__created_at", "number")[:PER_KIND]
    )
    for round_ in rounds:
        layout = round_.track_layout
        season = f"{round_.season.championship.name} {round_.season.name}"
        hits.append(
            Hit(
                "round",
                f"{layout.track.name} · {layout.name}",
                season,
                f"/rounds/{round_.id}",
                round_.number,
            )
        )

    drivers = DriverProfile.objects.filter(display_name__icontains=query)
    if not is_league_admin(user):
        # A driver page is open to the people who share a championship with the driver.
        drivers = drivers.filter(entries__season__championship__in=championships).distinct()
    for driver in drivers.order_by("display_name")[:PER_KIND]:
        hits.append(Hit("driver", driver.display_name, "", f"/drivers/{driver.id}"))
    return hits
