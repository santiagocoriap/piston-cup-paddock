"""Which drivers left the server before the end of the race, from the collector events.

A driver with fewer laps than the winner can be a lapped car or a DNF. A disconnect before the
end of the race, with no return, points to a DNF. The app only suggests it: an admin decides
(phase 3 of docs/plans/ac-integration.md).
"""

from datetime import timedelta

from apps.competition.models import Round
from apps.telemetry.script import Span, timeline

ROUND_WINDOW = timedelta(hours=12)


def _last_race(round_: Round, spans: list[Span]) -> Span | None:
    track = round_.track_layout.track.key
    races = [
        span
        for span in spans
        if span.session_type == "race"
        and span.track == track
        and abs(span.started_at - round_.scheduled_at) <= ROUND_WINDOW
    ]
    return max(races, key=lambda span: span.started_at) if races else None


def left_early(round_: Round, guids: set[str]) -> set[str]:
    """The GUIDs that disconnected during the last race start and did not come back before its
    end. Empty when the collector has no race of the round."""
    if round_.scheduled_at is None or not guids:
        return set()
    line = timeline(round_.season.championship, round_.scheduled_at)
    race = _last_race(round_, line.spans)
    if race is None:
        return set()
    found = set()
    for guid in guids:
        connections = [
            p
            for p in line.presences
            if (p.token_id, p.run_id) == (race.token_id, race.run_id)
            and p.guid == guid
            and (p.ended_at is None or p.ended_at > race.started_at)
            and (race.ended_at is None or p.started_at < race.ended_at)
        ]
        if not connections:
            continue
        last = max(connections, key=lambda p: p.started_at)
        if last.ended_at is not None and (race.ended_at is None or last.ended_at < race.ended_at):
            found.add(guid)
    return found
