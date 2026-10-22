"""Upload, preview, and apply an AC result file for a round."""

import hashlib
import json
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import change, record
from apps.competition.attempts import current_attempt, race_session
from apps.competition.models import Round, SeasonEntry, Session
from apps.handicaps.services import assigned_values
from apps.identity.models import DriverProfile
from apps.results.services import save_result
from apps.rules.scoring import Line, ResultError, Status

from .ac_results import ParsedSession, ResultFileError, is_steam_guid, parse
from .models import ImportedLap, ResultImport

MAX_BYTES = 5 * 1024 * 1024


def read_file(result_import: ResultImport) -> ParsedSession:
    with result_import.file.open("rb") as handle:
        return parse(json.loads(handle.read().decode("utf-8")))


def upload(round_: Round, filename: str, content: bytes, user) -> tuple[ResultImport, bool]:
    """Store the file as evidence. The same file for the same round gives the stored import.
    The second value is True when the file is new."""
    if len(content) > MAX_BYTES:
        raise ResultFileError("file_too_large")
    try:
        parsed = parse(json.loads(content.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResultFileError("not_json") from error
    sha256 = hashlib.sha256(content).hexdigest()
    existing = ResultImport.objects.filter(round=round_, sha256=sha256).first()
    if existing:
        return existing, False
    with transaction.atomic():
        result_import = ResultImport(
            round=round_,
            filename=filename[:255],
            sha256=sha256,
            session_type=parsed.session_type,
            uploaded_by=user,
        )
        result_import.file.save(filename, ContentFile(content), save=False)
        result_import.save()
        record(
            user,
            "import.uploaded",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={"number": round_.number, "track": str(round_.track_layout), "file": filename},
        )
    return result_import, True


@dataclass
class MatchedDriver:
    position: int
    guid: str
    name: str
    car_model: str
    laps: int
    total_time_ms: int
    best_lap_ms: int | None
    ballast_kg: int
    restrictor: int
    entry_id: int | None
    driver_name: str | None
    warnings: list[str] = field(default_factory=list)
    assigned_ballast_kg: int | None = None
    assigned_restrictor: int | None = None


@dataclass
class Preview:
    session_type: str
    track: str
    layout: str
    attempt: int | None
    drivers: list[MatchedDriver]
    unmatched: list[MatchedDriver]
    missing: list[str]
    warnings: list[str]


def preview(result_import: ResultImport) -> Preview:
    round_ = result_import.round
    parsed = read_file(result_import)
    entries = {
        e.driver.steam_guid: e
        for e in round_.season.entries.select_related("driver", "car")
        if e.driver.steam_guid
    }
    leader_laps = parsed.drivers[0].laps if parsed.drivers else 0
    assigned = assigned_values(round_) if parsed.session_type == "race" else {}
    matched, unmatched = [], []
    for position, driver in enumerate(parsed.drivers, start=1):
        entry = entries.get(driver.guid)
        row = MatchedDriver(
            position=position,
            guid=driver.guid,
            name=driver.name,
            car_model=driver.car_model,
            laps=driver.laps,
            total_time_ms=driver.total_time_ms,
            best_lap_ms=driver.best_lap_ms,
            ballast_kg=driver.ballast_kg,
            restrictor=driver.restrictor,
            entry_id=entry.id if entry else None,
            driver_name=entry.driver.display_name if entry else None,
        )
        if driver.result_guid and driver.result_guid != driver.guid:
            row.warnings.append("guid_differs_in_result")
        if entry and entry.car and entry.car.key.lower() != driver.car_model.lower():
            row.warnings.append("car_differs")
        if entry and parsed.session_type == "race":
            expected = assigned.get(entry.id)
            if expected:
                row.assigned_ballast_kg, row.assigned_restrictor = expected
                if (driver.ballast_kg, driver.restrictor) != expected:
                    row.warnings.append("handicap_differs")
        if parsed.session_type == "race" and driver.laps < leader_laps:
            row.warnings.append("fewer_laps")
        (matched if entry else unmatched).append(row)

    warnings = []
    layout = round_.track_layout
    if parsed.track != layout.track.key or parsed.layout != layout.key:
        warnings.append("track_differs")
    attempt = None
    if parsed.session_type == "race":
        attempt = current_attempt(race_session(round_)).number
    return Preview(
        session_type=parsed.session_type,
        track=parsed.track,
        layout=parsed.layout,
        attempt=attempt,
        drivers=matched,
        unmatched=unmatched,
        missing=parsed.missing,
        warnings=warnings,
    )


def link_guid(result_import: ResultImport, guid: str, entry_id: int, user) -> None:
    """Give a driver profile the Steam GUID from the file. Only a profile without a GUID."""
    if not is_steam_guid(guid):
        raise ResultFileError("bad_guid")
    entry = (
        SeasonEntry.objects.select_related("driver")
        .filter(pk=entry_id, season=result_import.round.season)
        .first()
    )
    if entry is None:
        raise ResultFileError("entry_not_in_season")
    profile = entry.driver
    if profile.steam_guid and profile.steam_guid != guid:
        raise ResultFileError("driver_has_other_guid")
    if DriverProfile.objects.filter(steam_guid=guid).exclude(pk=profile.pk).exists():
        raise ResultFileError("guid_belongs_to_other_driver")
    with transaction.atomic():
        profile.steam_guid = guid
        profile.save(update_fields=["steam_guid"])
        record(
            user,
            "driver.guid_linked",
            "driver",
            profile.id,
            params={"driver": profile.display_name},
            changes=[change("steam_guid", None, guid)],
        )


def _provisional_report(round_: Round, user) -> None:
    from apps.reports.services import auto_request

    auto_request(round_, user)


def apply(
    result_import: ResultImport, user, *, statuses: dict[int, str], ignored: list[str]
) -> ResultImport:
    """Store the laps. A race file also enters the classification as a result version.

    Every driver in the file needs a match, or the admin must ignore the GUID on purpose.
    """
    if result_import.status == ResultImport.State.APPLIED:
        raise ResultFileError("already_applied")
    view = preview(result_import)
    not_ignored = [d for d in view.unmatched if d.guid not in ignored]
    if not_ignored:
        raise ResultFileError("unmatched_drivers")
    round_ = result_import.round
    parsed = read_file(result_import)
    entry_by_guid = {d.guid: d.entry_id for d in view.drivers}

    with transaction.atomic():
        kind = {"race": Session.Kind.RACE, "qualifying": Session.Kind.QUALIFYING}.get(
            parsed.session_type, Session.Kind.PRACTICE
        )
        session, _ = Session.objects.get_or_create(round=round_, kind=kind)
        lap_counter: dict[str, int] = {}
        laps = []
        for lap in parsed.laps:
            if lap.guid in ignored:
                continue
            lap_counter[lap.guid] = lap_counter.get(lap.guid, 0) + 1
            laps.append(
                ImportedLap(
                    result_import=result_import,
                    entry_id=entry_by_guid.get(lap.guid),
                    guid=lap.guid,
                    lap_number=lap_counter[lap.guid],
                    lap_time_ms=lap.lap_time_ms,
                    sectors_ms=lap.sectors_ms,
                    cuts=lap.cuts,
                    tyre=lap.tyre,
                    ballast_kg=lap.ballast_kg,
                    restrictor=lap.restrictor,
                    timestamp_ms=lap.timestamp_ms,
                )
            )
        ImportedLap.objects.bulk_create(laps)

        if parsed.session_type == "race":
            lines = []
            for position, driver in enumerate(view.drivers, start=1):
                status = Status(statuses.get(driver.entry_id, Status.FINISHED))
                if status not in (Status.FINISHED, Status.DNF):
                    raise ResultError("import_status_not_allowed")
                lines.append(
                    Line(
                        driver.entry_id,
                        status,
                        position,
                        laps=driver.laps,
                        total_ms=driver.total_time_ms,
                    )
                )
            save_result(round_, lines, user, reason=f"Import: {result_import.filename}")

        result_import.session = session
        if parsed.session_type == "race":
            result_import.attempt = current_attempt(race_session(round_))
        result_import.status = ResultImport.State.APPLIED
        result_import.applied_at = timezone.now()
        result_import.save(update_fields=["session", "attempt", "status", "applied_at"])
        if kind == Session.Kind.RACE and round_.season.championship.provisional_reports:
            transaction.on_commit(lambda: _provisional_report(round_, user))
        record(
            user,
            "import.applied",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={
                "number": round_.number,
                "track": str(round_.track_layout),
                "file": result_import.filename,
                "session": parsed.session_type,
            },
            changes=[change("ignored", None, ", ".join(ignored) or None)],
        )
    return result_import
