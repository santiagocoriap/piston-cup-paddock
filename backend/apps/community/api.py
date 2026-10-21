from datetime import datetime
from typing import Literal

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.urls import public_url
from apps.competition.models import Round, Season, SeasonEntry
from apps.competition.permissions import can_view, visible_championships

from .models import Attendance, CalendarFeed, Notification
from .services import feed_for, ics, new_feed

router = Router(tags=["community"])


# Attendance


class AnswerIn(Schema):
    answer: Literal["yes", "maybe", "no"]


class AttendanceRowOut(Schema):
    entry_id: int
    driver_name: str
    answer: str | None


class AttendanceOut(Schema):
    mine: str | None
    can_answer: bool
    yes: int
    maybe: int
    no: int
    rows: list[AttendanceRowOut]


def _round(user, round_id: int) -> Round:
    round_ = get_object_or_404(
        Round.objects.select_related("season__championship", "track_layout__track"), pk=round_id
    )
    if not can_view(user, round_.season.championship):
        raise Http404
    return round_


def _my_entry(user, round_: Round) -> SeasonEntry | None:
    return SeasonEntry.objects.filter(season=round_.season, driver__user=user).first()


def attendance_out(user, round_: Round) -> AttendanceOut:
    answers = {a.entry_id: a.answer for a in round_.attendance.all()}
    mine = _my_entry(user, round_)
    rows = [
        AttendanceRowOut(entry_id=e.id, driver_name=e.driver.display_name, answer=answers.get(e.id))
        for e in round_.season.entries.select_related("driver").order_by("number")
    ]
    started = round_.scheduled_at is not None and round_.scheduled_at <= timezone.now()
    return AttendanceOut(
        mine=answers.get(mine.id) if mine else None,
        can_answer=mine is not None and not started,
        yes=sum(1 for r in rows if r.answer == "yes"),
        maybe=sum(1 for r in rows if r.answer == "maybe"),
        no=sum(1 for r in rows if r.answer == "no"),
        rows=rows,
    )


@router.get("/rounds/{round_id}/attendance", response=AttendanceOut)
def get_attendance(request, round_id: int):
    return attendance_out(request.user, _round(request.user, round_id))


@router.put("/rounds/{round_id}/attendance", response=AttendanceOut)
def answer(request, round_id: int, payload: AnswerIn):
    round_ = _round(request.user, round_id)
    entry = _my_entry(request.user, round_)
    if entry is None:
        raise HttpError(403, "not_in_season")
    if round_.scheduled_at is not None and round_.scheduled_at <= timezone.now():
        raise HttpError(422, "round_started")
    Attendance.objects.update_or_create(
        round=round_, entry=entry, defaults={"answer": payload.answer}
    )
    return attendance_out(request.user, round_)


# Calendar


def _ics_response(text: str, filename: str) -> HttpResponse:
    response = HttpResponse(text, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _base_url(request) -> str:
    return public_url(request)


@router.get("/seasons/{season_id}/calendar.ics")
def season_calendar(request, season_id: int):
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(request.user, season.championship):
        raise Http404
    rounds = season.rounds.select_related("season__championship", "track_layout__track")
    name = f"{season.championship.name} {season.name}"
    return _ics_response(ics(rounds.order_by("number"), _base_url(request), name), "calendar.ics")


@router.get("/rounds/{round_id}/calendar.ics")
def round_calendar(request, round_id: int):
    round_ = _round(request.user, round_id)
    name = f"{round_.season.championship.name} R{round_.number}"
    return _ics_response(ics([round_], _base_url(request), name), f"round-{round_.number}.ics")


class FeedOut(Schema):
    path: str  # Add the address of the app in front.


@router.get("/me/calendar-feed", response=FeedOut)
def my_feed(request):
    return FeedOut(path=f"/api/calendar/{feed_for(request.user).token}.ics")


@router.post("/me/calendar-feed", response=FeedOut)
def replace_feed(request):
    return FeedOut(path=f"/api/calendar/{new_feed(request.user).token}.ics")


@router.get("/calendar/{token}.ics", auth=None)
def feed(request, token: str):
    """All rounds of the championships that the owner of the token can see."""
    item = CalendarFeed.objects.filter(token=token).select_related("user").first()
    if item is None or not item.user.is_active:
        raise Http404
    rounds = (
        Round.objects.filter(season__championship__in=visible_championships(item.user))
        .select_related("season__championship", "track_layout__track")
        .order_by("scheduled_at")
    )
    return _ics_response(ics(rounds, _base_url(request), "Piston Cup Paddock"), "paddock.ics")


# Notifications


class NotificationOut(Schema):
    id: int
    kind: str
    params: dict
    link: str
    created_at: datetime
    read: bool


class NotificationsOut(Schema):
    unread: int
    items: list[NotificationOut]


class ReadIn(Schema):
    ids: list[int] = []  # Empty: mark all as read.


def _notifications(user) -> NotificationsOut:
    mine = Notification.objects.filter(user=user)
    return NotificationsOut(
        unread=mine.filter(read_at__isnull=True).count(),
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                params=n.params,
                link=n.link,
                created_at=n.created_at,
                read=n.read_at is not None,
            )
            for n in mine[:50]
        ],
    )


@router.get("/me/notifications", response=NotificationsOut)
def list_notifications(request):
    return _notifications(request.user)


@router.post("/me/notifications/read", response=NotificationsOut)
def read_notifications(request, payload: ReadIn):
    unread = Notification.objects.filter(user=request.user, read_at__isnull=True)
    if payload.ids:
        unread = unread.filter(id__in=payload.ids)
    unread.update(read_at=timezone.now())
    return _notifications(request.user)
