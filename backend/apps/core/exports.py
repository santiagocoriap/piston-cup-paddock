"""CSV exports of a season and of the track records."""

import csv
import io

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router

from apps.competition.models import Season
from apps.competition.permissions import can_view
from apps.records.services import record_boards
from apps.restarts.models import Restart
from apps.results.models import RaceResult
from apps.results.services import season_standings

router = Router(tags=["exports"])


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value):
    """Stop a text cell from running as a spreadsheet formula. Players choose their names in
    AC, so a name like "=HYPERLINK(...)" must stay text. Numbers stay numbers."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def _csv(filename: str, header: list[str], rows) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows([_cell(value) for value in row] for row in rows)
    # A byte order mark lets Excel open the file as UTF-8.
    response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _season(user, season_id: int) -> Season:
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(user, season.championship):
        raise Http404
    return season


def _slug(season: Season) -> str:
    return f"{season.championship.name}-{season.name}".replace(" ", "_")


@router.get("/seasons/{season_id}/export/results.csv")
def export_results(request, season_id: int):
    season = _season(request.user, season_id)
    rows = []
    results = (
        RaceResult.objects.filter(round__season=season, current_version__isnull=False)
        .select_related("round__track_layout__track", "current_version")
        .order_by("round__number")
    )
    for result in results:
        lines = result.current_version.lines.select_related("entry__driver", "entry__car")
        for line in sorted(lines, key=lambda r: (r.position is None, r.position or 0)):
            rows.append(
                [
                    result.round.number,
                    result.round.track_layout.track.name,
                    result.round.track_layout.name,
                    result.status,
                    result.current_version.number,
                    line.position or "",
                    line.status,
                    line.entry.number,
                    line.entry.driver.display_name,
                    line.entry.car_name,
                    line.points,
                ]
            )
    header = [
        "round",
        "track",
        "layout",
        "result_status",
        "version",
        "position",
        "status",
        "number",
        "driver",
        "car",
        "points",
    ]
    return _csv(f"{_slug(season)}-results.csv", header, rows)


@router.get("/seasons/{season_id}/export/standings.csv")
def export_standings(request, season_id: int):
    season = _season(request.user, season_id)
    entries = {e.id: e for e in season.entries.select_related("driver", "car")}
    table = season_standings(season)
    rounds = [score.round_number for score in table[0].rounds] if table else []
    rows = [
        [
            row.rank,
            entries[row.entry_id].number,
            entries[row.entry_id].driver.display_name,
            entries[row.entry_id].car_name,
            entries[row.entry_id].team,
            row.points,
            row.wins,
            *[score.points if score.status else "" for score in row.rounds],
        ]
        for row in table
    ]
    header = ["rank", "number", "driver", "car", "team", "points", "wins"]
    header += [f"R{n}" for n in rounds]
    return _csv(f"{_slug(season)}-standings.csv", header, rows)


@router.get("/seasons/{season_id}/export/restarts.csv")
def export_restarts(request, season_id: int):
    season = _season(request.user, season_id)
    restarts = (
        Restart.objects.filter(abandoned_attempt__session__round__season=season)
        .select_related(
            "abandoned_attempt__session__round__track_layout__track",
            "requested_by",
            "executed_by",
        )
        .prefetch_related("responsible_entries__driver")
        .order_by("abandoned_attempt__session__round__number", "abandoned_attempt__number")
    )
    rows = [
        [
            r.abandoned_attempt.session.round.number,
            r.abandoned_attempt.session.round.track_layout.track.name,
            r.abandoned_attempt.number,
            r.lap or "",
            r.elapsed_seconds or "",
            r.location,
            r.reason,
            r.explanation,
            r.requested_by.display_name if r.requested_by else "",
            r.executed_by.display_name if r.executed_by else "",
            r.responsibility,
            ", ".join(e.driver.display_name for e in r.responsible_entries.all()),
            r.review_status,
        ]
        for r in restarts
    ]
    header = [
        "round",
        "track",
        "abandoned_start",
        "lap",
        "elapsed_seconds",
        "location",
        "reason",
        "explanation",
        "requested_by",
        "executed_by",
        "responsibility",
        "responsible_drivers",
        "review_status",
    ]
    return _csv(f"{_slug(season)}-restarts.csv", header, rows)


@router.get("/records/export.csv")
def export_records(request):
    boards, details = record_boards(request.user)
    rows = []
    for board in boards:
        for holder in board.holders:
            lap = details[holder.lap_id]
            round_ = lap.result_import.round
            rows.append(
                [
                    round_.track_layout.track.name,
                    round_.track_layout.name,
                    lap.entry.car_name,
                    board.category,
                    board.record_ms,
                    holder.driver_name,
                    round_.season.championship.name,
                    round_.season.name,
                    round_.number,
                    holder.date.isoformat(),
                    lap.ballast_kg,
                    lap.restrictor,
                    lap.tyre,
                    "unknown",
                    lap.result_import.filename,
                ]
            )
    header = [
        "track",
        "layout",
        "car",
        "category",
        "lap_time_ms",
        "driver",
        "championship",
        "season",
        "round",
        "date",
        "ballast_kg",
        "restrictor_pct",
        "tyre",
        "conditions",
        "source_file",
    ]
    return _csv("records.csv", header, rows)
