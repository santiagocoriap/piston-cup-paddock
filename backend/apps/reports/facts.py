"""Collect the calculated facts of a round. The AI gets these facts and nothing else.

Each fact has a "ref", the source of the value in the app. The AI writes commentary. It does
not decide winners, points, penalties, responsibility, or standings. Those come from here.
"""

from apps.competition.models import Round, Session
from apps.imports.models import ImportedLap, ResultImport
from apps.restarts.models import Restart
from apps.restarts.services import summarize
from apps.results.models import RaceResult, ResultVersion
from apps.results.services import season_standings


def lap_time(ms: int | None) -> str | None:
    if ms is None:
        return None
    minutes, rest = divmod(ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def _classification(version: ResultVersion) -> list[dict]:
    rows = version.lines.select_related("entry__driver", "entry__car").order_by(
        "position", "entry__number"
    )
    return [
        {
            "ref": f"result_version:{version.id}:entry:{row.entry_id}",
            "position": row.position,
            "status": row.status,
            "driver": row.entry.driver.display_name,
            "number": row.entry.number,
            "car": row.entry.car.name,
            "points": row.points,
            "pole": row.pole,
            "fastest_lap": row.fastest_lap,
            "laps": row.laps,
            "total_time": lap_time(row.total_ms),
        }
        for row in rows
    ]


def _penalties(result: RaceResult) -> list[dict]:
    return [
        {
            "ref": f"penalty:{p.id}",
            "driver": p.entry.driver.display_name,
            "kind": p.kind,
            "value": p.value,
            "reason": p.reason,
            "source": p.source,
        }
        for p in result.penalties.select_related("entry__driver")
    ]


def _laps(round_: Round) -> list[dict]:
    race_import = (
        ResultImport.objects.filter(
            round=round_, session__kind=Session.Kind.RACE, status=ResultImport.State.APPLIED
        )
        .order_by("-applied_at")
        .first()
    )
    if race_import is None:
        return []
    by_entry: dict[int, list[ImportedLap]] = {}
    for lap in race_import.laps.filter(entry__isnull=False).select_related("entry__driver"):
        by_entry.setdefault(lap.entry_id, []).append(lap)
    stats = []
    for entry_id, laps in by_entry.items():
        valid = [lap for lap in laps if lap.cuts == 0 and not lap.invalid_reason]
        best = min(valid, key=lambda lap: lap.lap_time_ms) if valid else None
        stats.append(
            (
                best.lap_time_ms if best else 10**9,
                {
                    "ref": f"result_import:{race_import.id}:entry:{entry_id}",
                    "driver": laps[0].entry.driver.display_name,
                    "laps": len(laps),
                    "valid_laps": len(valid),
                    "cuts": sum(lap.cuts for lap in laps),
                    "best_lap": lap_time(best.lap_time_ms) if best else None,
                    "best_lap_number": best.lap_number if best else None,
                },
            )
        )
    return [item for _, item in sorted(stats, key=lambda pair: pair[0])]


def _restarts(round_: Round) -> dict:
    restarts = list(
        Restart.objects.filter(abandoned_attempt__session__round=round_)
        .select_related("abandoned_attempt")
        .prefetch_related("responsible_entries__driver")
    )
    items = []
    for restart in restarts:
        confirmed = restart.decided
        items.append(
            {
                "ref": f"restart:{restart.id}",
                "attempt": restart.abandoned_attempt.number,
                "reason": restart.reason,
                "lap": restart.lap,
                "elapsed_seconds": restart.elapsed_seconds,
                "review_status": restart.review_status,
                # Only a confirmed decision gives a cause. A pending or disputed restart gives
                # no names, so the text cannot blame a driver before the admins decide.
                "responsibility": restart.responsibility if confirmed else "not_decided",
                "responsible_drivers": (
                    [e.driver.display_name for e in restart.responsible_entries.all()]
                    if confirmed
                    else []
                ),
            }
        )
    summary = summarize(restarts)
    return {
        "ref": f"round:{round_.id}:restarts",
        "total": summary.total,
        "pending_or_disputed": summary.pending_or_disputed,
        "confirmed_caused": [
            {"driver": c.driver_name, "restarts": c.total, "shared": c.shared}
            for c in summary.caused
        ],
        "items": items,
    }


def _standings(round_: Round) -> list[dict]:
    season = round_.season
    names = {e.id: e.driver.display_name for e in season.entries.select_related("driver")}
    before = {row.entry_id: row for row in season_standings(season, up_to_round=round_.number - 1)}
    rows = []
    for row in season_standings(season, up_to_round=round_.number):
        earlier = before.get(row.entry_id)
        rows.append(
            {
                "ref": f"standings:season:{season.id}:after_round:{round_.number}",
                "rank": row.rank,
                "driver": names[row.entry_id],
                "points": row.points,
                "wins": row.wins,
                "rank_before": earlier.rank if earlier and round_.number > 1 else None,
                "points_before": earlier.points if earlier else 0,
            }
        )
    return rows


def _incidents(round_: Round) -> tuple[list[dict], bool]:
    """Contacts of the accepted race start. They do not say who caused a contact."""
    from apps.collectors.incident_api import accepted_race_incidents

    incidents, names, has_events = accepted_race_incidents(round_)
    return [
        {
            "ref": f"incident:{incident.key}",
            "lap": incident.events[0].lap,
            "type": "car_contact" if incident.kind == "car" else "track_contact",
            "drivers": sorted(names.get(car, car) for car in incident.cars),
            "impact_kmh": round(incident.max_speed),
        }
        for incident in incidents
    ], has_events


def _records(round_ids: set[int], layout_ids: set[int]) -> list[dict]:
    """Track records set or equaled in these rounds. Only official results set records."""
    from apps.records.boards import boards
    from apps.records.services import candidate_laps

    laps, details = candidate_laps(None)
    laps = [lap for lap in laps if lap.layout_id in layout_ids]
    rows = []
    for board in boards(laps):
        previous = None
        for item in board.history:
            if item.kind == "removed":
                continue
            if item.lap.round_id in round_ids:
                lap = details[item.lap.lap_id]
                rows.append(
                    {
                        "ref": f"imported_lap:{item.lap.lap_id}",
                        "driver": item.lap.driver_name,
                        "track": str(lap.result_import.round.track_layout),
                        "car": lap.entry.car.name,
                        "category": board.category,
                        "time": lap_time(item.lap.lap_time_ms),
                        "kind": "new_record" if item.kind == "record" else "equal_record",
                        "previous_record": lap_time(previous),
                    }
                )
            if item.kind == "record":
                previous = item.lap.lap_time_ms
    return rows


def round_facts(round_: Round) -> tuple[dict, ResultVersion | None]:
    """The facts of the round and the result version that they come from."""
    result = RaceResult.objects.filter(round=round_).select_related("current_version").first()
    version = result.current_version if result else None
    layout = round_.track_layout
    facts = {
        "round": {
            "ref": f"round:{round_.id}",
            "championship": round_.season.championship.name,
            "season": round_.season.name,
            "number": round_.number,
            "track": layout.track.name,
            "layout": layout.name,
            "date": round_.scheduled_at.date().isoformat() if round_.scheduled_at else None,
        },
        "result": None,
        "classification": [],
        "penalties": [],
        "laps": _laps(round_),
        "restarts": _restarts(round_),
        "standings": [],
        "incidents": [],
        "records": [],
        "data_gaps": [],
    }
    facts["incidents"], has_events = _incidents(round_)
    if version is None:
        facts["data_gaps"].append("no_result")
    else:
        facts["result"] = {
            "ref": f"result_version:{version.id}",
            "status": result.status,
            "version": version.number,
        }
        facts["classification"] = _classification(version)
        facts["penalties"] = _penalties(result)
        facts["standings"] = _standings(round_)
        if result.status == RaceResult.State.OFFICIAL:
            facts["records"] = _records({round_.id}, {round_.track_layout_id})
        else:
            facts["data_gaps"].append("records_after_official_result")
    if not facts["laps"]:
        facts["data_gaps"].append("no_lap_data")
    if not has_events:
        facts["data_gaps"].append("no_incident_data")
    return facts, version


def season_facts(season) -> dict:
    """The facts of a season from its official rounds. A round without official result does not
    count. A season with no lap data gets a data gap, so the text stays a standings recap."""
    official = list(
        season.rounds.filter(result__status=RaceResult.State.OFFICIAL)
        .select_related("track_layout__track", "result__current_version")
        .order_by("number")
    )
    names = {e.id: e.driver.display_name for e in season.entries.select_related("driver")}
    table = season_standings(season, official_only=True)
    standings = []
    for row in table:
        scores = [s for s in row.rounds if s.status is not None and s.official]
        standings.append(
            {
                "ref": f"standings:season:{season.id}:official",
                "rank": row.rank,
                "driver": names[row.entry_id],
                "points": row.points,
                "wins": row.wins,
                "podiums": sum(1 for s in scores if s.position and s.position <= 3),
                "starts": sum(1 for s in scores if s.status != "dns"),
            }
        )
    rounds = []
    for round_ in official:
        version = round_.result.current_version
        winner = (
            version.lines.filter(position=1).select_related("entry__driver").first()
            if version
            else None
        )
        rounds.append(
            {
                "ref": f"result_version:{version.id}" if version else f"round:{round_.id}",
                "number": round_.number,
                "track": round_.track_layout.track.name,
                "layout": round_.track_layout.name,
                "winner": winner.entry.driver.display_name if winner else None,
                "fastest_lap": _fastest_lap(round_),
            }
        )
    restarts = summarize(
        list(
            Restart.objects.filter(abandoned_attempt__session__round__in=official).prefetch_related(
                "responsible_entries__driver"
            )
        )
    )
    remaining = max(season.planned_round_count - len(official), 0)
    incident_counts: dict[str, int] = {}
    any_events = False
    for round_ in official:
        incidents, has_events = _incidents(round_)
        any_events = any_events or has_events
        for incident in incidents:
            for name in incident["drivers"]:
                incident_counts[name] = incident_counts.get(name, 0) + 1
    progression = []
    for round_ in official:
        after = season_standings(season, up_to_round=round_.number, official_only=True)
        leaders = [names[row.entry_id] for row in after if row.rank == 1]
        progression.append(
            {
                "ref": f"standings:season:{season.id}:after_round:{round_.number}",
                "round": round_.number,
                "leaders": leaders,
                "points": after[0].points if after else 0,
            }
        )
    from apps.collectors.safety_api import season_ratings

    safety = [
        {
            "ref": f"safety:season:{season.id}:entry:{entry.id}",
            "driver": entry.driver.display_name,
            "rating": rating.rating,
            "status": rating.status,
            "incidents_this_season": incident_counts.get(entry.driver.display_name, 0),
        }
        for entry, rating in season_ratings(season)
        if rating.status != "unknown"
    ]
    gaps = []
    if not official:
        gaps.append("no_official_rounds")
    if not any(r["fastest_lap"] for r in rounds):
        gaps.append("no_race_details")
    if not any_events:
        gaps.append("no_incident_data")
    return {
        "season": {
            "ref": f"season:{season.id}",
            "championship": season.championship.name,
            "name": season.name,
            "planned_rounds": season.planned_round_count,
            "official_rounds": len(official),
            "finished": remaining == 0,
        },
        "champion": (
            [s["driver"] for s in standings if s["rank"] == 1] if remaining == 0 and table else []
        ),
        "standings": standings,
        "rounds": rounds,
        "restarts": {
            "ref": f"season:{season.id}:restarts",
            "total": restarts.total,
            "pending_or_disputed": restarts.pending_or_disputed,
            "confirmed_caused": [
                {"driver": c.driver_name, "restarts": c.total, "shared": c.shared}
                for c in restarts.caused
            ],
        },
        "title_progression": progression,
        "records": _records({r.id for r in official}, {r.track_layout_id for r in official}),
        "safety": safety,
        "data_gaps": gaps,
    }


def _fastest_lap(round_: Round) -> dict | None:
    """The fastest valid lap of the race file of the round."""
    lap = (
        ImportedLap.objects.filter(
            result_import__round=round_,
            result_import__session__kind=Session.Kind.RACE,
            result_import__status=ResultImport.State.APPLIED,
            entry__isnull=False,
            cuts=0,
            invalid_reason="",
        )
        .select_related("entry__driver")
        .order_by("lap_time_ms")
        .first()
    )
    if lap is None:
        return None
    return {
        "ref": f"imported_lap:{lap.id}",
        "driver": lap.entry.driver.display_name,
        "time": lap_time(lap.lap_time_ms),
    }
