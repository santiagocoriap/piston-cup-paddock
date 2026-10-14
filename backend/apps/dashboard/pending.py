"""What waits for an admin: results to approve, collector files with a problem, protests,
ballots, accounts, and images.

Each kind counts only what the user manages. A kind with nothing in it is not in the list.
"""

from dataclasses import dataclass, field

from apps.catalog.models import Car, TrackLayout
from apps.competition.models import Championship, ChampionshipMember
from apps.competition.permissions import is_league_admin
from apps.identity.accounts import can_make_accounts, can_manage_user
from apps.identity.models import User
from apps.imports.models import ResultImport
from apps.results.models import Protest, RaceResult
from apps.voting.models import Ballot

# The home page shows this many items of each kind. The count gives the full number.
MAX_ITEMS = 5


@dataclass
class PendingItem:
    path: str
    name: str
    championship: str | None = None
    number: int | None = None  # The round number, for a round.


@dataclass
class Pending:
    kind: str
    count: int
    items: list[PendingItem] = field(default_factory=list)


def managed_championships(user):
    if is_league_admin(user):
        return Championship.objects.all()
    return Championship.objects.filter(
        members__user=user, members__role=ChampionshipMember.Role.ADMIN
    ).distinct()


def _round_item(round_) -> PendingItem:
    layout = round_.track_layout
    return PendingItem(
        path=f"/rounds/{round_.id}",
        name=f"{layout.track.name} · {layout.name}",
        championship=round_.season.championship.name,
        number=round_.number,
    )


def _add(found: list[Pending], kind: str, rows: list, item) -> None:
    if rows:
        found.append(Pending(kind, len(rows), [item(row) for row in rows[:MAX_ITEMS]]))


def pending(user) -> list[Pending]:
    found: list[Pending] = []
    managed = managed_championships(user)
    in_managed = {"round__season__championship__in": managed, "round__cancelled_at__isnull": True}
    related = ("round__season__championship", "round__track_layout__track")

    results = list(
        RaceResult.objects.filter(
            status__in=[RaceResult.State.PROVISIONAL, RaceResult.State.UNDER_REVIEW], **in_managed
        )
        .select_related(*related)
        .order_by("round__scheduled_at", "round__number")
    )
    _add(found, "results", results, lambda r: _round_item(r.round))

    # Collector files that the app did not publish by itself, because of a problem.
    blocked = list(
        ResultImport.objects.filter(
            status=ResultImport.State.PREVIEW,
            auto_status=ResultImport.AutoState.BLOCKED,
            **in_managed,
        )
        .select_related(*related)
        .order_by("uploaded_at")
    )
    _add(found, "imports", blocked, lambda i: _round_item(i.round))

    protests = list(
        Protest.objects.filter(
            status=Protest.State.OPEN,
            **{f"result__{key}": value for key, value in in_managed.items()},
        )
        .select_related(*(f"result__{name}" for name in related))
        .order_by("created_at")
    )
    _add(found, "protests", protests, lambda p: _round_item(p.result.round))

    for kind, state in (
        ("ballots_closed", Ballot.State.CLOSED),
        ("ballots_open", Ballot.State.OPEN),
    ):
        ballots = list(
            Ballot.objects.filter(status=state, season__championship__in=managed)
            .select_related("season__championship")
            .order_by("closes_at", "id")
        )
        _add(
            found,
            kind,
            ballots,
            lambda b: PendingItem(
                path=f"/ballots/{b.id}", name=b.title, championship=b.season.championship.name
            ),
        )

    if can_make_accounts(user):
        waiting = [
            account
            for account in User.objects.filter(is_active=True).order_by("username")
            if not account.has_usable_password() and can_manage_user(user, account)
        ]
        _add(
            found,
            "accounts",
            waiting,
            lambda u: PendingItem(path="/admin/accounts", name=u.username),
        )

    if is_league_admin(user):
        missing = (
            TrackLayout.objects.filter(outline="").count() + Car.objects.filter(preview="").count()
        )
        if missing:
            found.append(Pending("images", missing))
    return found
