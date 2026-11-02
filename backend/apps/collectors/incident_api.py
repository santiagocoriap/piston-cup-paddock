"""Incidents of a round from the collector events, and the steward review of each one."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.audit.services import record
from apps.competition.models import Round
from apps.competition.permissions import can, can_view
from apps.identity.models import by_guid

from .incidents import GAP_SECONDS, Collision, Incident, group
from .models import CollectorEvent, IncidentReview

router = Router(tags=["incidents"])

WINDOW = timedelta(hours=12)
AC_SESSION_TYPES = {1: "practice", 2: "qualifying", 3: "race"}


def _car(data: dict | None) -> str | None:
    if not data:
        return None
    return data.get("guid") or f"car:{data.get('car_id')}"


def collisions(round_: Round, session: str) -> tuple[list[Collision], dict[str, str], bool]:
    """The collision events of the round night, with attempt and lap. Also the names of the
    cars, and if the round has any collector event at all."""
    if round_.scheduled_at is None:
        return [], {}, False
    events = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
    ).order_by("occurred_at", "token_id", "run_id", "seq")
    names: dict[str, str] = {
        guid: e.driver.display_name
        for guid, e in by_guid(round_.season.entries.select_related("driver")).items()
    }
    found: list[Collision] = []
    current = ""
    attempts: dict[str, int] = defaultdict(int)
    laps: dict[str, int] = defaultdict(int)
    any_event = False
    for event in events:
        any_event = True
        data = event.data or {}
        if event.kind == "session_started":
            current = AC_SESSION_TYPES.get(data.get("type"), "")
            attempts[current] += 1
            laps.clear()
        elif event.kind == "lap_completed":
            laps[_car(data)] += 1
        elif event.kind in ("collision_car", "collision_env") and current == session:
            car = _car(data)
            if data.get("name") and car not in names:
                names[car] = data["name"]
            found.append(
                Collision(
                    id=event.id,
                    at=event.occurred_at,
                    kind=event.kind,
                    car=car,
                    other=_car(data.get("other")),
                    speed_kmh=float(data.get("speed_kmh") or 0),
                    x=data.get("x"),
                    z=data.get("z"),
                    attempt=attempts[current],
                    lap=laps[car] + 1,
                )
            )
    return found, names, any_event


def session_starts(round_: Round, session: str) -> int:
    """How many times the server started this session on the round night. The last start is
    the one that counts: each earlier start ended with a restart."""
    if round_.scheduled_at is None:
        return 0
    started = CollectorEvent.objects.filter(
        token__championship_id=round_.season.championship_id,
        occurred_at__gte=round_.scheduled_at - WINDOW,
        occurred_at__lte=round_.scheduled_at + WINDOW,
        kind="session_started",
    ).values_list("data", flat=True)
    wanted = {name: number for number, name in AC_SESSION_TYPES.items()}[session]
    return sum(1 for data in started if (data or {}).get("type") == wanted)


def accepted_race_incidents(round_: Round) -> tuple[list[Incident], dict[str, str], bool]:
    """The incidents of the last race start (the accepted race), the car names, and if the
    round has any collector event. An incident of a start before a restart does not count."""
    found, names, has_events = collisions(round_, "race")
    accepted = session_starts(round_, "race")
    return [i for i in group(found) if i.events[0].attempt == accepted], names, has_events


def night_incidents(
    round_: Round, sessions: tuple[str, ...] = ("qualifying", "race")
) -> tuple[list[tuple[str, Incident]], dict[str, str], bool]:
    """The incidents of every start of these sessions, with the session of each. A start that
    ended with a restart counts too: a crash before a restart is still a crash."""
    found: list[tuple[str, Incident]] = []
    names: dict[str, str] = {}
    has_events = False
    for session in sessions:
        collisions_of, more_names, any_event = collisions(round_, session)
        has_events = has_events or any_event
        names.update(more_names)
        found += [(session, incident) for incident in group(collisions_of)]
    return found, names, has_events


class EventOut(Schema):
    id: int
    at: datetime
    kind: str
    car: str
    other: str | None
    speed_kmh: float


class ReviewOut(Schema):
    outcome: str
    note: str
    reviewed_by: str | None
    reviewed_at: datetime


class IncidentOut(Schema):
    key: int
    started_at: datetime
    kind: str
    attempt: int
    lap: int | None
    cars: list[str]
    max_speed: float
    x: float | None
    z: float | None
    events: list[EventOut]
    review: ReviewOut | None


class IncidentsOut(Schema):
    session: str
    gap_seconds: float
    has_events: bool
    can_review: bool
    # The number of the last start. An incident of an earlier start is from before a restart.
    last_start: int
    incidents: list[IncidentOut]


class ReviewIn(Schema):
    outcome: Literal["open", "no_action", "racing_incident", "penalty"]
    note: str = Field("", max_length=1000)


def _incident_out(incident: Incident, names: dict, reviews: dict) -> IncidentOut:
    first = incident.events[0]
    review = reviews.get(incident.key)

    def name(car: str | None) -> str | None:
        return names.get(car, car) if car else None

    return IncidentOut(
        key=incident.key,
        started_at=first.at,
        kind=incident.kind,
        attempt=first.attempt,
        lap=first.lap,
        cars=sorted(name(car) for car in incident.cars),
        max_speed=round(incident.max_speed, 1),
        x=first.x,
        z=first.z,
        events=[
            EventOut(
                id=e.id,
                at=e.at,
                kind=e.kind,
                car=name(e.car),
                other=name(e.other),
                speed_kmh=e.speed_kmh,
            )
            for e in incident.events
        ],
        review=ReviewOut(
            outcome=review.outcome,
            note=review.note,
            reviewed_by=review.reviewed_by.username if review.reviewed_by else None,
            reviewed_at=review.reviewed_at,
        )
        if review
        else None,
    )


def _round(user, round_id: int) -> Round:
    round_ = get_object_or_404(Round.objects.select_related("season__championship"), pk=round_id)
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _incidents_out(user, round_: Round, session: str) -> IncidentsOut:
    found, names, any_event = collisions(round_, session)
    reviews = {r.incident_key: r for r in round_.incident_reviews.select_related("reviewed_by")}
    return IncidentsOut(
        session=session,
        gap_seconds=GAP_SECONDS,
        has_events=any_event,
        can_review=can(user, round_.season.championship, "penalties"),
        last_start=session_starts(round_, session),
        incidents=[_incident_out(i, names, reviews) for i in group(found)],
    )


@router.get("/rounds/{round_id}/incidents", response=IncidentsOut)
def get_incidents(
    request, round_id: int, session: Literal["race", "qualifying", "practice"] = "race"
):
    return _incidents_out(request.user, _round(request.user, round_id), session)


@router.put("/rounds/{round_id}/incidents/{key}/review", response=IncidentsOut)
def review_incident(request, round_id: int, key: int, payload: ReviewIn):
    round_ = _round(request.user, round_id)
    if not can(request.user, round_.season.championship, "penalties"):
        raise HttpError(403, "forbidden")
    found, _, _ = collisions(round_, "race")
    keys = {i.key for i in group(found)}
    for session in ("qualifying", "practice"):
        keys |= {i.key for i in group(collisions(round_, session)[0])}
    if key not in keys:
        raise HttpError(404, "incident_not_found")
    with transaction.atomic():
        IncidentReview.objects.update_or_create(
            round=round_,
            incident_key=key,
            defaults={
                "outcome": payload.outcome,
                "note": payload.note,
                "reviewed_by": request.user,
            },
        )
        record(
            request.user,
            "incident.reviewed",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={"number": round_.number, "incident": key, "outcome": payload.outcome},
            reason=payload.note,
        )
    return _incidents_out(request.user, round_, "race")
