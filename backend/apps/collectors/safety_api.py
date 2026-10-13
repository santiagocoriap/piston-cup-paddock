"""Safety ratings of the drivers of a season. The rating counts every round of the
championship, in date order, so it goes on from season to season."""

from collections import defaultdict
from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from apps.competition.models import Championship, Round, Season, Session
from apps.competition.permissions import can_view, visible_championships
from apps.imports.models import ImportedLap, ResultImport
from apps.rules.safety import (
    PROVISIONAL_LAPS,
    RULES_VERSION,
    RoundInput,
    incident_points,
    rate,
)

from .incident_api import accepted_race_incidents

router = Router(tags=["safety"])


def _round_inputs(round_: Round) -> dict[str, RoundInput]:
    """For each GUID: laps of the accepted race start and its incidents."""
    label = f"{round_.season.name} R{round_.number} {round_.track_layout.track.name}"
    race_import = (
        ResultImport.objects.filter(
            round=round_, session__kind=Session.Kind.RACE, status=ResultImport.State.APPLIED
        )
        .order_by("-applied_at")
        .first()
    )
    laps: dict[str, int] = defaultdict(int)
    if race_import:
        for guid in ImportedLap.objects.filter(result_import=race_import).values_list(
            "guid", flat=True
        ):
            laps[guid] += 1
    incidents, names, has_events = accepted_race_incidents(round_)
    inputs = {guid: RoundInput(round_.id, label, count, has_events) for guid, count in laps.items()}
    for incident in incidents:
        others = sorted(names.get(car, car) for car in incident.cars)
        for car in incident.cars:
            if car not in inputs:
                continue
            points = incident_points(incident.kind, incident.max_speed)
            text = (
                f"{points} pts · lap {incident.events[0].lap} · {incident.kind} · "
                f"{round(incident.max_speed)} km/h · {' + '.join(others)}"
            )
            inputs[car].incidents.append((incident.kind, incident.max_speed, text))
    return inputs


class ChangeOut(Schema):
    round_id: int
    label: str
    status: str
    laps: int
    points: int
    change: float
    rating_after: float
    explanation: list[str]


class DriverSafetyOut(Schema):
    entry_id: int
    driver_name: str
    rating: float
    status: str
    laps: int
    points: int
    per_100_laps: float | None
    history: list[ChangeOut]


class SafetyOut(Schema):
    rules_version: str
    provisional_laps: int
    computed_at: datetime
    drivers: list[DriverSafetyOut]


@router.get("/seasons/{season_id}/safety", response=SafetyOut)
def season_safety(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    rounds = (
        Round.objects.filter(season__championship=season.championship, result__isnull=False)
        .select_related("season", "track_layout__track")
        .order_by("scheduled_at", "season__created_at", "number")
    )
    by_round = [_round_inputs(r) for r in rounds]
    drivers = []
    for entry in season.entries.select_related("driver").order_by("number"):
        guid = entry.driver.steam_guid
        rating = rate([inputs[guid] for inputs in by_round if guid and guid in inputs])
        drivers.append(
            DriverSafetyOut(
                entry_id=entry.id,
                driver_name=entry.driver.display_name,
                rating=rating.rating,
                status=rating.status,
                laps=rating.laps,
                points=rating.points,
                per_100_laps=rating.per_100_laps,
                history=[ChangeOut(**vars(change)) for change in rating.history],
            )
        )
    drivers.sort(key=lambda d: (d.status == "unknown", -d.rating))
    return SafetyOut(
        rules_version=RULES_VERSION,
        provisional_laps=PROVISIONAL_LAPS,
        computed_at=timezone.now(),
        drivers=drivers,
    )


def driver_ratings(user, driver) -> list[tuple[str, object]]:
    """The safety rating of one driver in each championship the user can see."""
    guid = driver.steam_guid
    championships = Championship.objects.filter(
        seasons__entries__driver=driver, pk__in=visible_championships(user)
    ).distinct()
    result = []
    for championship in championships:
        rounds = (
            Round.objects.filter(season__championship=championship, result__isnull=False)
            .select_related("season", "track_layout__track")
            .order_by("scheduled_at", "season__created_at", "number")
        )
        inputs = [_round_inputs(r) for r in rounds]
        result.append((championship.name, rate([i[guid] for i in inputs if guid and guid in i])))
    return result
