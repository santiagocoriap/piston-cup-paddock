"""Receive files and events from a server collector.

A collector can only add raw evidence. It finds no users and changes no seasons. The app finds
the round from the time and the track of the file. When the championship allows it, a clean file
becomes a provisional result with no admin click (apps/imports/auto_publish.py). A file with a
problem waits for an admin.
"""

import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.services import record
from apps.competition.models import Championship, Round
from apps.imports import auto_publish, penalty_services
from apps.imports import services as imports
from apps.imports.ac_results import parse, track_key
from apps.imports.models import PenaltyLogFile, ResultImport
from apps.imports.real_penalty import parse as parse_log

from .models import CollectorEvent, CollectorFile, CollectorToken

log = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
MAX_EVENTS = 500  # In one batch.
MATCH_WINDOW = timedelta(hours=12)
RESULT_NAME = re.compile(r"(\d{4})_(\d{1,2})_(\d{1,2})_(\d{1,2})_(\d{1,2})_([A-Z]+)")


class CollectorError(ValueError):
    pass


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_token(championship: Championship, name: str, user) -> tuple[CollectorToken, str]:
    """Make a key. The app shows the raw key one time only."""
    raw = "pcc_" + secrets.token_urlsafe(32)
    with transaction.atomic():
        token = CollectorToken.objects.create(
            championship=championship, name=name, token_hash=_hash(raw), created_by=user
        )
        record(
            user,
            "collector.created",
            "championship",
            championship.id,
            championship=championship,
            params={"name": name},
        )
    return token, raw


USER_AGENT = re.compile(r"paddock-collector/(\d+\.\d+\.\d+)")


def remember_version(token: CollectorToken, user_agent: str) -> None:
    match = USER_AGENT.search(user_agent)
    if match and match[1] != token.version:
        token.version = match[1]
        CollectorToken.objects.filter(pk=token.pk).update(version=match[1])


def save_status(token: CollectorToken, queued: int, error: str, error_at) -> None:
    token.queued_files = queued
    token.last_error = error.strip()[:200]
    token.last_error_at = error_at if token.last_error else None
    token.save(update_fields=["queued_files", "last_error", "last_error_at"])


def key_matches(token: CollectorToken, raw: str) -> bool:
    return hmac.compare_digest(token.token_hash, _hash(raw.strip()))


def revoke_token(token: CollectorToken, user) -> None:
    with transaction.atomic():
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        record(
            user,
            "collector.revoked",
            "championship",
            token.championship_id,
            championship=token.championship,
            params={"name": token.name},
        )


def authenticate(raw: str) -> CollectorToken | None:
    token = (
        CollectorToken.objects.filter(token_hash=_hash(raw), revoked_at__isnull=True)
        .select_related("championship__league")
        .first()
    )
    if token:
        CollectorToken.objects.filter(pk=token.pk).update(last_seen_at=timezone.now())
    return token


def _read(kind: str, filename: str, content: bytes, tz: ZoneInfo) -> tuple[str, str, datetime]:
    """The session type, the track key, and the session time of a file."""
    text = content.decode("utf-8", errors="replace")
    if kind == CollectorFile.Kind.RESULT:
        parsed = parse(json.loads(text))
        match = RESULT_NAME.search(filename)
        if not match:
            raise CollectorError("unknown_file_time")
        year, month, day, hour, minute = (int(v) for v in match.groups()[:5])
        # The AC server writes the local time of the server, with no zone: the league timezone.
        when = datetime(year, month, day, hour, minute, tzinfo=tz)
        return parsed.session_type, parsed.track, when
    log = parse_log(text)
    track = track_key(log.track.split(" / ")[0].strip())
    return log.session_type, track, timezone.make_aware(log.started_at, tz)


def _find_round(championship: Championship, track: str, when: datetime) -> Round | None:
    rounds = list(
        Round.objects.filter(
            season__championship=championship,
            scheduled_at__gte=when - MATCH_WINDOW,
            scheduled_at__lte=when + MATCH_WINDOW,
            track_layout__track__key=track,
        )
    )
    return rounds[0] if len(rounds) == 1 else None


def receive_file(
    token: CollectorToken, kind: str, filename: str, content: bytes
) -> tuple[CollectorFile, bool]:
    if len(content) > MAX_BYTES:
        raise CollectorError("file_too_large")
    if kind not in CollectorFile.Kind.values:
        raise CollectorError("unknown_kind")
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:255]
    sha256 = hashlib.sha256(content).hexdigest()
    existing = CollectorFile.objects.filter(token=token, sha256=sha256).first()
    if existing:
        return existing, False
    item = CollectorFile(token=token, kind=kind, filename=filename, sha256=sha256)
    tz = ZoneInfo(token.championship.league.timezone)
    try:
        item.session_type, item.track, item.session_time = _read(kind, filename, content, tz)
    except (ValueError, KeyError, TypeError) as error:
        # ResultFileError, PenaltyLogError, CollectorError, and bad JSON are ValueErrors.
        item.status = CollectorFile.State.FAILED
        item.error = getattr(error, "code", None) or "not_readable"
    item.file.save(filename, ContentFile(content), save=False)
    with transaction.atomic():
        if item.status != CollectorFile.State.FAILED:
            round_ = _find_round(token.championship, item.track, item.session_time)
            item.status = CollectorFile.State.UNMATCHED
            item.save()
            if round_:
                _assign(item, round_, content, None)
        else:
            item.save()
    if item.status == CollectorFile.State.ASSIGNED:
        _publish(item)
    return item, True


def _publish(item: CollectorFile) -> None:
    """Publish the file with no admin click when it has no problem. The file is already safe:
    an error here never loses it, and an admin can still apply it by hand."""
    try:
        if item.kind == CollectorFile.Kind.RESULT:
            result_import = item.round.imports.filter(sha256=item.sha256).first()
            if result_import:
                auto_publish.auto_apply(result_import)
        else:
            auto_publish.auto_penalties(item.round)
    except Exception:
        log.exception("Automatic publication failed for collector file %s", item.id)


def _assign(item: CollectorFile, round_: Round, content: bytes, user) -> None:
    """Make the import preview of the round. An admin applies it later."""
    item.round = round_
    item.status = CollectorFile.State.ASSIGNED
    item.error = ""
    if item.kind == CollectorFile.Kind.RESULT:
        imports.upload(round_, item.filename, content, user)
    else:
        # Real Penalty writes a log while the session runs. A newer copy of the same log
        # replaces the preview copy. An applied log never changes.
        same = PenaltyLogFile.objects.filter(round=round_, filename=item.filename)
        if same.filter(status=ResultImport.State.APPLIED).exclude(sha256=item.sha256).exists():
            item.status = CollectorFile.State.FAILED
            item.error = "log_already_applied"
        else:
            older = same.exclude(sha256=item.sha256)
            CollectorFile.objects.filter(
                token=item.token, round=round_, filename=item.filename
            ).exclude(pk=item.pk).update(status=CollectorFile.State.REPLACED)
            older.delete()
            penalty_services.upload_log(round_, item.filename, content, user)
    item.save()


def assign(item: CollectorFile, round_: Round, user) -> CollectorFile:
    """An admin chooses the round of an unmatched file."""
    if round_.season.championship_id != item.token.championship_id:
        raise CollectorError("round_not_in_championship")
    if item.status not in (CollectorFile.State.UNMATCHED, CollectorFile.State.ASSIGNED):
        raise CollectorError("file_not_assignable")
    with item.file.open("rb") as handle:
        content = handle.read()
    with transaction.atomic():
        _assign(item, round_, content, user)
        record(
            user,
            "collector.file_assigned",
            "round",
            round_.id,
            championship=round_.season.championship,
            params={"filename": item.filename, "number": round_.number},
        )
    return item


def receive_events(token: CollectorToken, run_id: str, events: list[dict]) -> int:
    """Store the events. An event that came before adds nothing. Gives the count of new events."""
    if len(events) > MAX_EVENTS:
        raise CollectorError("too_many_events")
    rows = []
    for event in events:
        occurred = parse_datetime(str(event.get("at", "")))
        if occurred is None or timezone.is_naive(occurred):
            raise CollectorError("event_time_required")
        rows.append(
            CollectorEvent(
                token=token,
                run_id=run_id[:40],
                seq=int(event["seq"]),
                kind=str(event.get("kind", ""))[:30],
                occurred_at=occurred,
                data=event.get("data") or {},
            )
        )
    before = CollectorEvent.objects.filter(token=token, run_id=run_id).count()
    CollectorEvent.objects.bulk_create(rows, ignore_conflicts=True)
    added = CollectorEvent.objects.filter(token=token, run_id=run_id).count() - before
    if added:
        _match_script_laps(token)
    return added


def _match_script_laps(token: CollectorToken) -> None:
    """New server events can be the missing part for laps of the Paddock script that wait."""
    from apps.telemetry import script

    try:
        script.rematch(token.championship)
    except Exception:
        log.exception("Matching the script laps failed for collector %s", token.id)
