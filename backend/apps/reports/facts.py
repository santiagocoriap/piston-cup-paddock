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
        confirmed = restart.review_status == Restart.Review.CONFIRMED
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
        "data_gaps": [],
    }
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
    if not facts["laps"]:
        facts["data_gaps"].append("no_lap_data")
    facts["data_gaps"].append("no_incident_data")
    return facts, version
