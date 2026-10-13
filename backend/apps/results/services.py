"""Race results: versions, penalties, protests, approval, and standings."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.audit.services import change, record
from apps.competition.attempts import accept_current_attempt, current_attempt, race_session
from apps.competition.models import Round, Season, SeasonEntry
from apps.rules.models import RulesVersion
from apps.rules.scoring import (
    Line,
    PenaltyKind,
    PenaltyRule,
    PointsRules,
    ResultError,
    Status,
    has_times,
    penalized_points,
    standings,
    validate,
)
from apps.rules.title import Contender, TitleScenarios
from apps.rules.title import scenarios as title_math

from .models import Penalty, Protest, RaceResult, ResultLine, ResultVersion

State = RaceResult.State


# Reading the stored data


def entered_lines(version: ResultVersion) -> list[Line]:
    return [
        Line(
            row.entry_id,
            Status(row.entered_status),
            row.entered_position,
            row.pole,
            row.fastest_lap,
            row.laps,
            row.total_ms,
        )
        for row in version.lines.all()
    ]


def final_line(row: ResultLine) -> Line:
    return Line(row.entry_id, Status(row.status), row.position, row.pole, row.fastest_lap)


def penalty_rules(result: RaceResult) -> list[PenaltyRule]:
    return [PenaltyRule(p.entry_id, PenaltyKind(p.kind), p.value) for p in result.penalties.all()]


def protest_deadline(result: RaceResult):
    if result.published_at is None:
        return None
    return result.published_at + timedelta(minutes=result.round.season.protest_window_minutes)


def current_lines(**filters):
    """Result lines of the current version of each result."""
    return ResultLine.objects.filter(version__result__current_version=F("version"), **filters)


# Writing versions


def _audit_params(round_: Round) -> dict:
    return {
        "season": round_.season.name,
        "number": round_.number,
        "track": str(round_.track_layout),
    }


def _line_value(row) -> dict | None:
    if row is None:
        return None
    return {"status": row.status, "position": row.position, "points": row.points}


def _write_version(
    result: RaceResult, lines: list[Line], kind: str, user, reason: str
) -> ResultVersion:
    """Make the next version from the entered lines and all penalties of the result."""
    rules_version = RulesVersion.current_for(result.round.season)
    final, points = penalized_points(lines, penalty_rules(result), rules_version.as_points_rules())
    final_by_entry = {line.entry_id: line for line in final}
    last = result.versions.order_by("-number").values_list("number", flat=True).first()
    version = ResultVersion.objects.create(
        result=result,
        number=(last or 0) + 1,
        kind=kind,
        rules_version=rules_version,
        reason=reason,
        created_by=user,
    )
    ResultLine.objects.bulk_create(
        ResultLine(
            version=version,
            entry_id=line.entry_id,
            entered_status=line.status,
            entered_position=line.position,
            status=final_by_entry[line.entry_id].status,
            position=final_by_entry[line.entry_id].position,
            pole=line.pole,
            fastest_lap=line.fastest_lap,
            points=points[line.entry_id],
            laps=line.laps,
            total_ms=line.total_ms,
        )
        for line in lines
    )
    result.current_version = version
    result.save(update_fields=["current_version", "updated_at"])
    return version


def _changes(round_: Round, before: ResultVersion | None, after: ResultVersion) -> list[dict]:
    drivers = dict(round_.season.entries.values_list("id", "driver__display_name"))
    old = {row.entry_id: row for row in before.lines.all()} if before else {}
    new = {row.entry_id: row for row in after.lines.all()}
    changes = []
    for entry_id in sorted(set(old) | set(new), key=lambda e: drivers.get(e, "")):
        old_value, new_value = _line_value(old.get(entry_id)), _line_value(new.get(entry_id))
        if old_value != new_value:
            changes.append(change(drivers.get(entry_id, str(entry_id)), old_value, new_value))
    return changes


def _same_lines(old: list[Line], new: list[Line]) -> bool:
    return sorted(old, key=lambda line: line.entry_id) == sorted(
        new, key=lambda line: line.entry_id
    )


def save_result(round_: Round, lines: list[Line], user, reason: str = "") -> RaceResult:
    """Enter or correct the classification. A correction of an official result needs a reason."""
    entry_ids = set(round_.season.entries.values_list("id", flat=True))
    if any(line.entry_id not in entry_ids for line in lines):
        raise ResultError("entry_not_in_season")
    validate(lines)

    with transaction.atomic():
        result = RaceResult.objects.select_for_update().filter(round=round_).first()
        if result and result.status == State.OFFICIAL and not reason.strip():
            raise ResultError("reason_required")
        before = result.current_version if result else None
        if before is not None and _same_lines(entered_lines(before), lines):
            return result  # Nothing changed. A second save of the same lines adds nothing.
        if result is None:
            # Keep the handicaps of this race before its first result counts.
            from apps.handicaps.services import save_used_values

            save_used_values(round_)
            result = RaceResult.objects.create(round=round_, published_at=timezone.now())
        kind = ResultVersion.Kind.ENTRY if before is None else ResultVersion.Kind.CORRECTION
        version = _write_version(result, lines, kind, user, reason)
        accept_current_attempt(round_)  # Points come only from the accepted attempt.
        record(
            user,
            "result.saved" if before is None else "result.changed",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={**_audit_params(round_), "version": version.number},
            changes=_changes(round_, before, version),
            reason=reason,
        )
        if before is None:
            _notify_season(round_, "result.published")
    return result


def _notify_season(round_: Round, kind: str) -> None:
    from apps.community.services import notify, round_params, season_user_ids

    notify(season_user_ids(round_.season), kind, round_params(round_), f"/rounds/{round_.id}")


def add_penalty(
    result: RaceResult,
    entry: SeasonEntry,
    kind: str,
    value: int,
    reason: str,
    user,
    *,
    source: str = Penalty.Source.STEWARD,
    external_id: str | None = None,
    protest: Protest | None = None,
) -> Penalty:
    """Add a penalty and make a new version. A known external ID gives back the stored penalty."""
    if not reason.strip():
        raise ResultError("reason_required")
    if kind in (PenaltyKind.POSITIONS, PenaltyKind.POINTS, PenaltyKind.TIME) and value < 1:
        raise ResultError("penalty_value_required")
    if entry.season_id != result.round.season_id:
        raise ResultError("entry_not_in_season")
    with transaction.atomic():
        result = RaceResult.objects.select_for_update().get(pk=result.pk)
        if external_id:
            existing = result.penalties.filter(external_id=external_id).first()
            if existing:
                return existing
        before = result.current_version
        if kind == PenaltyKind.TIME and not has_times(entered_lines(before)):
            raise ResultError("time_penalty_needs_times")
        penalty = Penalty.objects.create(
            result=result,
            attempt=current_attempt(race_session(result.round)),
            entry=entry,
            kind=kind,
            value=value if kind not in (PenaltyKind.DSQ, PenaltyKind.SERVED) else 0,
            reason=reason,
            source=source,
            external_id=external_id,
            protest=protest,
            created_by=user,
        )
        if kind == PenaltyKind.SERVED:
            # A served penalty is history only. The result does not change, so no new version.
            record(
                user,
                "penalty.served",
                "round",
                result.round_id,
                championship=result.round.season.championship,
                params={**_audit_params(result.round), "driver": entry.driver.display_name},
                reason=reason,
            )
            return penalty
        version = _write_version(
            result, entered_lines(before), ResultVersion.Kind.PENALTY, user, reason
        )
        record(
            user,
            "penalty.added",
            "round",
            result.round_id,
            championship=result.round.season.championship,
            params={
                **_audit_params(result.round),
                "driver": entry.driver.display_name,
                "kind": kind,
                "value": penalty.value,
                "version": version.number,
            },
            changes=_changes(result.round, before, version),
            reason=reason,
        )
    return penalty


def submit_protest(result: RaceResult, user, *, description: str, entry_ids: list[int], lap):
    if result.status == State.OFFICIAL:
        raise ResultError("result_is_official")
    deadline = protest_deadline(result)
    if deadline and timezone.now() > deadline:
        raise ResultError("protest_window_closed")
    if not description.strip():
        raise ResultError("description_required")
    entries = list(SeasonEntry.objects.filter(season=result.round.season, id__in=entry_ids))
    if len(entries) != len(set(entry_ids)):
        raise ResultError("entry_not_in_season")
    with transaction.atomic():
        protest = Protest.objects.create(
            result=result,
            attempt=current_attempt(race_session(result.round)),
            submitted_by=user,
            lap=lap,
            description=description,
        )
        protest.involved.set(entries)
        old_status = result.status
        result.status = State.UNDER_REVIEW
        result.save(update_fields=["status", "updated_at"])
        record(
            user,
            "protest.submitted",
            "round",
            result.round_id,
            championship=result.round.season.championship,
            params={**_audit_params(result.round), "protest": protest.id},
            changes=[change("status", old_status, result.status)],
            reason=description,
        )
    from apps.community.services import notify, round_params, staff_user_ids

    round_ = result.round
    notify(
        staff_user_ids(round_.season, "penalties"),
        "protest.new",
        round_params(round_),
        f"/rounds/{round_.id}",
    )
    return protest


def decide_protest(
    protest: Protest, user, *, outcome: str, decision: str, penalty: dict | None = None
) -> Protest:
    """Close a protest. An upheld protest can add a penalty. With no open protest left, the
    result goes back to provisional and waits for the approval."""
    if protest.status != Protest.State.OPEN:
        raise ResultError("protest_already_decided")
    if not decision.strip():
        raise ResultError("reason_required")
    if penalty and outcome != Protest.State.UPHELD:
        raise ResultError("penalty_needs_upheld_protest")
    result = protest.result
    with transaction.atomic():
        protest.status = outcome
        protest.decision = decision
        protest.decided_by = user
        protest.decided_at = timezone.now()
        protest.save(update_fields=["status", "decision", "decided_by", "decided_at"])
        record(
            user,
            "protest.decided",
            "round",
            result.round_id,
            championship=result.round.season.championship,
            params={**_audit_params(result.round), "protest": protest.id, "outcome": outcome},
            reason=decision,
        )
        if penalty:
            entry = SeasonEntry.objects.filter(
                pk=penalty["entry_id"], season=result.round.season
            ).first()
            if entry is None:
                raise ResultError("entry_not_in_season")
            add_penalty(
                result,
                entry,
                penalty["kind"],
                penalty.get("value", 0),
                decision,
                user,
                protest=protest,
            )
        result.refresh_from_db()
        still_open = result.protests.filter(status=Protest.State.OPEN).exists()
        if result.status == State.UNDER_REVIEW and not still_open:
            result.status = State.PROVISIONAL
            result.save(update_fields=["status", "updated_at"])
    from apps.community.services import notify, round_params

    round_ = protest.result.round
    notify(
        [protest.submitted_by_id],
        "protest.decided",
        {**round_params(round_), "outcome": protest.status},
        f"/rounds/{round_.id}",
    )
    return protest


def approve_result(result: RaceResult, user) -> RaceResult:
    if result.status == State.OFFICIAL:
        raise ResultError("result_is_official")
    if result.protests.filter(status=Protest.State.OPEN).exists():
        raise ResultError("open_protests")
    with transaction.atomic():
        old_status = result.status
        result.status = State.OFFICIAL
        result.approved_at = timezone.now()
        result.approved_by = user
        result.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
        record(
            user,
            "result.approved",
            "round",
            result.round_id,
            championship=result.round.season.championship,
            params={**_audit_params(result.round), "version": result.current_version.number},
            changes=[change("status", old_status, result.status)],
        )
        _notify_season(result.round, "result.official")
    return result


# Standings and career


@dataclass
class RoundScore:
    round_number: int
    status: str | None
    position: int | None
    points: int
    official: bool


@dataclass
class SeasonStanding:
    rank: int
    entry_id: int
    points: int
    wins: int
    rounds: list[RoundScore]


def season_standings(
    season: Season, up_to_round: int | None = None, official_only: bool = False
) -> list[SeasonStanding]:
    """The standings from the current version of each round result. With up_to_round, only
    the rounds with that number or lower count. With official_only, only official results."""
    rounds = season.rounds.filter(cancelled_at__isnull=True).order_by("number")
    lines = current_lines(
        version__result__round__season=season, version__result__round__cancelled_at__isnull=True
    )
    if official_only:
        lines = lines.filter(version__result__status=State.OFFICIAL)
    if up_to_round is not None:
        rounds = rounds.filter(number__lte=up_to_round)
        lines = lines.filter(version__result__round__number__lte=up_to_round)
    rounds = list(rounds)
    results = {r.round_id: r for r in RaceResult.objects.filter(round__season=season)}
    lines_by_round: dict[int, list[ResultLine]] = {r.id: [] for r in rounds}
    for row in lines.select_related("version__result"):
        lines_by_round[row.version.result.round_id].append(row)

    races = [
        ([final_line(row) for row in rows], {row.entry_id: row.points for row in rows})
        for rows in lines_by_round.values()
        if rows
    ]
    table = standings(list(season.entries.values_list("id", flat=True)), races)

    def score(round_: Round, entry_id: int) -> RoundScore:
        official = round_.id in results and results[round_.id].status == State.OFFICIAL
        row = next((r for r in lines_by_round[round_.id] if r.entry_id == entry_id), None)
        if row is None:
            return RoundScore(round_.number, None, None, 0, official)
        return RoundScore(round_.number, row.status, row.position, row.points, official)

    return [
        SeasonStanding(
            rank=row.rank,
            entry_id=row.entry_id,
            points=row.points,
            wins=row.wins,
            rounds=[score(r, row.entry_id) for r in rounds],
        )
        for row in table
    ]


@dataclass
class SeasonTitle:
    planned_rounds: int
    rounds_with_result: int
    scenarios: TitleScenarios
    limits: list[str]


def title_scenarios(season: Season) -> SeasonTitle:
    """Who can still win the title, with the rules of the standings and the current rules."""
    table = season_standings(season)
    done = {score.round_number for row in table for score in row.rounds if score.status is not None}
    cancelled = season.rounds.filter(cancelled_at__isnull=False).count()
    remaining = max(season.planned_round_count - len(done) - cancelled, 0)
    contenders = [
        Contender(
            row.entry_id,
            row.points,
            Counter(s.position for s in row.rounds if s.position is not None),
        )
        for row in table
    ]
    rules = RulesVersion.current_for(season)
    limits = []
    if RulesVersion.objects.filter(season=season).count() > 1:
        limits.append("rules_changed")
    if any(score.status is not None and not score.official for r in table for score in r.rounds):
        limits.append("provisional_results")
    return SeasonTitle(
        season.planned_round_count,
        len(done),
        title_math(contenders, rules.as_points_rules(), remaining),
        limits,
    )


def career_points(driver_ids: list[int]) -> dict[int, int]:
    """Official points of each driver over all seasons, from the current result versions."""
    rows = (
        current_lines(entry__driver_id__in=driver_ids, version__result__status=State.OFFICIAL)
        .values("entry__driver_id")
        .annotate(total=Sum("points"))
    )
    totals = {driver_id: 0 for driver_id in driver_ids}
    totals.update({row["entry__driver_id"]: row["total"] for row in rows})
    return totals


# Rules changes


@dataclass
class PreviewRow:
    entry_id: int
    current_rank: int
    current_points: int
    new_rank: int
    new_points: int


def preview_rules(season: Season, rules: PointsRules) -> list[PreviewRow]:
    """The standings with other points rules, next to the current standings. The same entered
    lines and penalties give the new points, so the preview changes nothing."""
    results = RaceResult.objects.filter(
        round__season=season, current_version__isnull=False
    ).select_related("current_version")
    races = []
    for result in results:
        final, points = penalized_points(
            entered_lines(result.current_version), penalty_rules(result), rules
        )
        races.append((final, points))
    new = {
        row.entry_id: row for row in standings(season.entries.values_list("id", flat=True), races)
    }
    return [
        PreviewRow(
            row.entry_id, row.rank, row.points, new[row.entry_id].rank, new[row.entry_id].points
        )
        for row in season_standings(season)
    ]


def change_rules(
    season: Season, user, fields: dict, reason: str, recalculate: bool
) -> RulesVersion:
    """Save a new rules version. With recalculate, every result of the season gets a new
    version with the new rules. Without it, only later results use them."""
    current = RulesVersion.current_for(season)
    with transaction.atomic():
        version = RulesVersion.objects.create(
            season=season,
            number=current.number + 1,
            reason=reason,
            recalculated=recalculate,
            created_by=user,
            **fields,
        )
        changes = [
            change(name, getattr(current, name), value)
            for name, value in fields.items()
            if getattr(current, name) != value
        ]
        record(
            user,
            "rules.changed",
            "season",
            season.id,
            championship=season.championship,
            params={"season": season.name, "version": version.number},
            changes=changes,
            reason=reason,
        )
        if recalculate:
            for result in RaceResult.objects.filter(
                round__season=season, current_version__isnull=False
            ).select_related("round", "current_version"):
                before = result.current_version
                after = _write_version(
                    result,
                    entered_lines(before),
                    ResultVersion.Kind.CORRECTION,
                    user,
                    f"Rules version {version.number}: {reason}",
                )
                record(
                    user,
                    "result.recalculated",
                    "round",
                    result.round_id,
                    championship=season.championship,
                    params={**_audit_params(result.round), "version": version.number},
                    changes=_changes(result.round, before, after),
                    reason=reason,
                )
    return version
