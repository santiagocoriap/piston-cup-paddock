"""Phase 6 of docs/plans/ac-integration.md: an alert when a race has no result file.

Three hours after the start of a round, the race result file should be in the app. If it is
not, the results admins of the championship get one notification. Only championships with a
collector get it: without a collector, the results come by hand.
"""

from datetime import timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.community.models import Notification
from apps.community.services import notify, round_params, staff_user_ids
from apps.competition.models import Round, Session
from apps.imports.models import ResultImport

from .models import CollectorFile, CollectorToken

KIND = "collector.no_results"
AFTER = timedelta(hours=3)
LOOK_BACK = timedelta(hours=24)  # Older rounds do not get a late alert.


def _has_race_file(round_: Round) -> bool:
    if ResultImport.objects.filter(round=round_, session__kind=Session.Kind.RACE).exists():
        return True
    return CollectorFile.objects.filter(
        round=round_, kind=CollectorFile.Kind.RESULT, session_type__iexact="race"
    ).exists()


def check_missing_results(now=None) -> int:
    """Send the alerts that are due. Gives the count of rounds with an alert."""
    now = now or timezone.now()
    active = CollectorToken.objects.filter(
        championship=OuterRef("season__championship"), revoked_at__isnull=True
    )
    rounds = (
        Round.objects.filter(scheduled_at__lte=now - AFTER, scheduled_at__gte=now - LOOK_BACK)
        .filter(Exists(active))
        .select_related("season__championship", "track_layout__track")
    )
    sent = 0
    for round_ in rounds:
        link = f"/rounds/{round_.id}"
        if _has_race_file(round_) or Notification.objects.filter(kind=KIND, link=link).exists():
            continue
        notify(staff_user_ids(round_.season, "results"), KIND, round_params(round_), link)
        sent += 1
    return sent
