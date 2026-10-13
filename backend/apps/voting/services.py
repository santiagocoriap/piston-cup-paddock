"""Season ballots for tracks and car classes."""

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.audit.services import change, record
from apps.catalog.models import TrackLayout
from apps.competition.calendar import fixed_layout_ids, next_round_number, voted_slots
from apps.competition.models import ChampionshipMember, Round, Season
from apps.results.services import current_lines
from apps.rules.scoring import Status

from .models import Ballot, BallotOption, BallotVoter, Vote
from .tally import decide

DEFAULT_ROLES = [ChampionshipMember.Role.DRIVER, ChampionshipMember.Role.ADMIN]


class BallotError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BallotError(code)


def _audit(user, action: str, ballot: Ballot, *, changes=None, reason: str = "") -> None:
    record(
        user,
        action,
        "ballot",
        ballot.id,
        championship=ballot.season.championship,
        params={"ballot": ballot.title, "season": ballot.season.name},
        changes=changes or [],
        reason=reason,
    )


SETTINGS = (
    "title",
    "method",
    "selection_limit",
    "slots",
    "choice_visibility",
    "totals_visibility",
    "allow_vote_changes",
    "closes_at",
    "eligible_roles",
    "prior_season_id",
    "min_prior_starts",
    "max_runoffs",
    "power_overrides",
)


def _check_settings(ballot: Ballot) -> None:
    if ballot.prior_season_id is not None:
        # Only a season of the same championship. Other championships stay out of scope.
        same = Season.objects.filter(
            pk=ballot.prior_season_id, championship_id=ballot.season.championship_id
        ).exclude(pk=ballot.season_id)
        _require(same.exists(), "bad_prior_season")
    _require(ballot.selection_limit >= 1, "selection_limit_too_small")
    if ballot.method == Ballot.Method.SINGLE:
        ballot.selection_limit = 1
    _require(all(int(power) >= 0 for power in ballot.power_overrides.values()), "bad_power")
    if not ballot.eligible_roles:
        ballot.eligible_roles = list(DEFAULT_ROLES)


def create_ballot(season: Season, user, kind: str, settings: dict) -> Ballot:
    ballot = Ballot(season=season, kind=kind, created_by=user)
    for key, value in settings.items():
        if key in SETTINGS and value is not None:
            setattr(ballot, key, value)
    _check_settings(ballot)
    with transaction.atomic():
        ballot.save()
        _audit(user, "ballot.created", ballot)
    return ballot


def update_ballot(ballot: Ballot, user, settings: dict) -> Ballot:
    _require(ballot.status == Ballot.State.DRAFT, "ballot_not_draft")
    changes = []
    for key, value in settings.items():
        if key in SETTINGS and value is not None and getattr(ballot, key) != value:
            changes.append(change(key, _plain(getattr(ballot, key)), _plain(value)))
            setattr(ballot, key, value)
    _check_settings(ballot)
    with transaction.atomic():
        ballot.save()
        _audit(user, "ballot.changed", ballot, changes=changes)
    return ballot


def _plain(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def add_option(ballot: Ballot, user, *, label: str = "", layout_id: int | None = None):
    _require(ballot.status == Ballot.State.DRAFT, "ballot_not_draft")
    layout = None
    if ballot.kind == Ballot.Kind.TRACK:
        _require(layout_id is not None, "layout_required")
        layout = TrackLayout.objects.select_related("track").filter(pk=layout_id).first()
        _require(layout is not None, "layout_required")
        repeats = ballot.season.allow_repeat_layouts
        _require(repeats or layout.id not in fixed_layout_ids(ballot.season), "layout_is_fixed")
        label = label or str(layout)
    _require(bool(label.strip()), "label_required")
    _require(not ballot.options.filter(label=label).exists(), "option_exists")
    with transaction.atomic():
        option = BallotOption.objects.create(ballot=ballot, label=label, track_layout=layout)
        _audit(user, "ballot.option_added", ballot, changes=[change("option", None, label)])
    return option


def remove_option(option: BallotOption, user) -> None:
    ballot = option.ballot
    _require(ballot.status == Ballot.State.DRAFT, "ballot_not_draft")
    with transaction.atomic():
        option.delete()
        _audit(
            user, "ballot.option_removed", ballot, changes=[change("option", option.label, None)]
        )


def _prior_starts(season: Season, user_ids: set[int]) -> dict[int, int]:
    """Races that each user started in the season, from the current result versions."""
    rows = (
        current_lines(version__result__round__season=season, entry__driver__user_id__in=user_ids)
        .exclude(status=Status.DNS)
        .values("entry__driver__user_id")
        .annotate(starts=Count("id"))
    )
    return {row["entry__driver__user_id"]: row["starts"] for row in rows}


def eligible_voters(ballot: Ballot) -> dict[int, int]:
    """The users who can vote, with their power. The app freezes this list at the opening."""
    members = ChampionshipMember.objects.filter(
        championship=ballot.season.championship, role__in=ballot.eligible_roles
    )
    user_ids = set(members.values_list("user_id", flat=True))
    if ballot.prior_season_id and ballot.min_prior_starts > 0:
        starts = _prior_starts(ballot.prior_season, user_ids)
        user_ids = {u for u in user_ids if starts.get(u, 0) >= ballot.min_prior_starts}
    overrides = {int(k): int(v) for k, v in ballot.power_overrides.items()}
    return {user_id: overrides.get(user_id, 1) for user_id in sorted(user_ids)}


def open_ballot(ballot: Ballot, user) -> Ballot:
    _require(ballot.status == Ballot.State.DRAFT, "ballot_not_draft")
    if ballot.kind == Ballot.Kind.TRACK and ballot.parent_id is None:
        ballot.slots = voted_slots(ballot.season)
        _require(ballot.slots >= 1, "no_voted_slots")
    _require(ballot.options.exists(), "no_options")
    voters = eligible_voters(ballot)
    _require(bool(voters), "no_voters")
    with transaction.atomic():
        BallotVoter.objects.bulk_create(
            BallotVoter(ballot=ballot, user_id=user_id, power=power)
            for user_id, power in voters.items()
        )
        ballot.status = Ballot.State.OPEN
        ballot.opened_at = timezone.now()
        ballot.save(update_fields=["status", "opened_at", "slots"])
        _audit(
            user,
            "ballot.opened",
            ballot,
            changes=[change("voters", None, len(voters)), change("slots", None, ballot.slots)],
        )
        _notify_voters(ballot, voters)
    return ballot


def _notify_voters(ballot: Ballot, user_ids) -> None:
    from apps.community.services import notify

    notify(
        user_ids,
        "ballot.open",
        {"season": ballot.season.name, "kind": ballot.kind},
        f"/ballots/{ballot.id}",
    )


def cast_vote(ballot: Ballot, user, option_ids: list[int]) -> None:
    _require(ballot.status == Ballot.State.OPEN, "ballot_not_open")
    _require(
        ballot.closes_at is None or timezone.now() <= ballot.closes_at, "ballot_deadline_passed"
    )
    voter = BallotVoter.objects.filter(ballot=ballot, user=user).first()
    _require(voter is not None, "not_a_voter")
    _require(voter.power > 0, "not_a_voter")
    chosen = set(option_ids)
    _require(len(chosen) == len(option_ids), "duplicate_choice")
    _require(len(chosen) >= 1, "choice_required")
    _require(len(chosen) <= ballot.selection_limit, "too_many_choices")
    options = list(ballot.options.filter(id__in=chosen))
    _require(len(options) == len(chosen), "option_not_in_ballot")
    already = voter.votes.exists()
    _require(not already or ballot.allow_vote_changes, "vote_change_not_allowed")
    with transaction.atomic():
        voter.votes.all().delete()
        Vote.objects.bulk_create(Vote(voter=voter, option=option) for option in options)


def totals(ballot: Ballot) -> dict[int, int]:
    """Weighted votes for each option."""
    result = {option.id: 0 for option in ballot.options.all()}
    for vote in Vote.objects.filter(option__ballot=ballot).select_related("voter"):
        result[vote.option_id] += vote.voter.power
    return result


def _select(options, source: str) -> None:
    for option in options:
        option.selected = True
        option.selected_by = source
        option.save(update_fields=["selected", "selected_by"])


def close_ballot(ballot: Ballot, user, *, reason: str = "") -> Ballot:
    """Close the vote and count it. A tie at the cut waits for a runoff or an admin choice."""
    _require(ballot.status == Ballot.State.OPEN, "ballot_not_open")
    early = ballot.closes_at is not None and timezone.now() < ballot.closes_at
    _require(not early or bool(reason.strip()), "reason_required")
    outcome = decide(totals(ballot), ballot.slots)
    with transaction.atomic():
        ballot.status = Ballot.State.CLOSED
        ballot.closed_at = timezone.now()
        ballot.closed_early = early
        ballot.close_reason = reason
        ballot.save(update_fields=["status", "closed_at", "closed_early", "close_reason"])
        _select(ballot.options.filter(id__in=outcome.winners), BallotOption.Source.VOTE)
        _audit(user, "ballot.closed", ballot, reason=reason)
        if not outcome.tied:
            _finish(ballot, user)
    return ballot


def tie(ballot: Ballot) -> tuple[list[BallotOption], int]:
    """The tied options and the slots that they compete for, for a closed ballot."""
    if ballot.status != Ballot.State.CLOSED:
        return [], 0
    outcome = decide(totals(ballot), ballot.slots)
    return list(ballot.options.filter(id__in=outcome.tied)), outcome.open_slots


def start_runoff(ballot: Ballot, user) -> Ballot:
    """A new ballot with only the tied options, the same voters, and the same rules."""
    tied, open_slots = tie(ballot)
    _require(bool(tied), "no_tie")
    _require(
        not ballot.runoffs.filter(status__in=["draft", "open", "closed"]).exists(), "runoff_exists"
    )
    depth = ballot.runoff_depth() + 1
    root = ballot
    while root.parent_id:
        root = root.parent
    _require(root.max_runoffs is None or depth <= root.max_runoffs, "runoff_limit_reached")
    with transaction.atomic():
        runoff = Ballot.objects.create(
            season=ballot.season,
            kind=ballot.kind,
            title=f"{root.title} · runoff {depth}",
            status=Ballot.State.OPEN,
            method=ballot.method,
            selection_limit=min(ballot.selection_limit, open_slots),
            slots=open_slots,
            choice_visibility=ballot.choice_visibility,
            totals_visibility=ballot.totals_visibility,
            allow_vote_changes=ballot.allow_vote_changes,
            eligible_roles=ballot.eligible_roles,
            power_overrides=ballot.power_overrides,
            parent=ballot,
            max_runoffs=ballot.max_runoffs,
            opened_at=timezone.now(),
            created_by=user,
        )
        for option in tied:
            BallotOption.objects.create(
                ballot=runoff, label=option.label, track_layout=option.track_layout, origin=option
            )
        BallotVoter.objects.bulk_create(
            BallotVoter(ballot=runoff, user_id=v.user_id, power=v.power)
            for v in ballot.voters.all()
        )
        _audit(
            user, "ballot.runoff_started", ballot, changes=[change("runoff", None, runoff.title)]
        )
    _notify_voters(runoff, runoff.voters.values_list("user_id", flat=True))
    return runoff


def decide_manually(ballot: Ballot, user, option_ids: list[int], reason: str) -> Ballot:
    """An admin picks the remaining winners. The submitted votes stay."""
    _require(ballot.status in (Ballot.State.OPEN, Ballot.State.CLOSED), "ballot_decided")
    _require(bool(reason.strip()), "reason_required")
    remaining = ballot.slots - ballot.options.filter(selected=True).count()
    chosen = list(ballot.options.filter(id__in=set(option_ids), selected=False))
    _require(len(chosen) == len(set(option_ids)) == remaining, "wrong_number_of_choices")
    with transaction.atomic():
        if ballot.status == Ballot.State.OPEN:
            ballot.closed_early = True
            ballot.closed_at = timezone.now()
        ballot.status = Ballot.State.CLOSED
        ballot.close_reason = reason
        ballot.save(update_fields=["status", "closed_early", "closed_at", "close_reason"])
        _select(chosen, BallotOption.Source.ADMIN)
        _audit(
            user,
            "ballot.decided_by_admin",
            ballot,
            changes=[change("selected", None, ", ".join(o.label for o in chosen))],
            reason=reason,
        )
        _finish(ballot, user)
    return ballot


def _finish(ballot: Ballot, user) -> None:
    """Mark the ballot as decided. A runoff passes its winners to the parent ballot.
    A decided track ballot adds the winners to the calendar as voted rounds."""
    ballot.status = Ballot.State.DECIDED
    ballot.save(update_fields=["status"])
    if ballot.parent_id:
        parent = ballot.parent
        winners = [o.origin for o in ballot.options.filter(selected=True) if o.origin]
        _select(winners, BallotOption.Source.RUNOFF)
        if parent.options.filter(selected=True).count() >= parent.slots:
            _finish(parent, user)
        return
    if ballot.kind == Ballot.Kind.TRACK:
        for option in ballot.options.filter(selected=True).select_related("track_layout"):
            Round.objects.create(
                season=ballot.season,
                number=next_round_number(ballot.season),
                track_layout=option.track_layout,
                scheduled_at=None,
                origin=Round.Origin.VOTED,
            )
    _audit(
        user,
        "ballot.decided",
        ballot,
        changes=[
            change(
                "selected",
                None,
                ", ".join(o.label for o in ballot.options.filter(selected=True)),
            )
        ],
    )


def voted_counts(ballot: Ballot) -> tuple[int, int]:
    """Voters who voted, and all voters."""
    voters = ballot.voters.annotate(n=Count("votes"))
    return voters.filter(n__gt=0).count(), voters.count()
