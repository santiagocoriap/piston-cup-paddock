from datetime import datetime
from typing import Literal

from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from pydantic import AwareDatetime

from apps.catalog.models import Car, CarClass, TrackLayout, with_subclasses
from apps.competition.calendar import fixed_layout_ids
from apps.competition.models import Season
from apps.competition.permissions import can_manage, can_view

from .models import Ballot, BallotOption, BallotVoter, Vote
from .services import (
    BallotError,
    add_option,
    cast_vote,
    choice_limit,
    close_ballot,
    create_ballot,
    decide_manually,
    layout_problem,
    open_ballot,
    remind,
    remove_option,
    set_options,
    start_runoff,
    tie,
    totals,
    update_ballot,
    voted_counts,
)

router = Router(tags=["voting"])


class BallotSettingsIn(Schema):
    title: str | None = Field(None, min_length=1, max_length=150)
    method: Ballot.Method | None = None
    selection_limit: int | None = Field(None, ge=1, le=50)
    slots: int | None = Field(None, ge=1, le=50)
    choice_visibility: Ballot.ChoiceVisibility | None = None
    totals_visibility: Ballot.TotalsVisibility | None = None
    allow_vote_changes: bool | None = None
    closes_at: AwareDatetime | None = None
    eligible_roles: list[str] | None = None
    prior_season_id: int | None = None
    min_prior_starts: int | None = Field(None, ge=0, le=100)
    max_runoffs: int | None = Field(None, ge=0, le=20)
    power_overrides: dict[str, int] | None = None
    choice_overrides: dict[str, int] | None = None
    opens_at: AwareDatetime | None = None
    remind_hours_before: int | None = Field(None, ge=0, le=168)
    min_participation_pct: int | None = Field(None, ge=0, le=100)
    low_participation_action: Literal["admin", "count"] | None = None
    show_voter_names: bool | None = None
    excluded_track_ids: list[int] | None = None
    class_rounds: bool | None = None


class BallotIn(BallotSettingsIn):
    # A plain literal: the enum name "Kind" also exists for penalties in the API schema.
    kind: Literal["track", "car_class"]
    title: str = Field(min_length=1, max_length=150)


class OptionIn(Schema):
    label: str = Field("", max_length=150)
    track_layout_id: int | None = None
    car_class_id: int | None = None


class VoteIn(Schema):
    option_ids: list[int]


class CloseIn(Schema):
    reason: str = Field("", max_length=500)


class DecideIn(Schema):
    option_ids: list[int]
    reason: str = Field(max_length=500)


class OptionOut(Schema):
    id: int
    label: str
    track_layout_id: int | None
    car_class_id: int | None = None
    selected: bool
    selected_by: str
    votes: int | None  # None when the totals are hidden from this user.
    voters: list[str] | None  # None when the choices are hidden from this user.
    # The picture of the track layout, or of the first car of the class. None without a picture.
    image_url: str | None = None
    # A car class: the pictures of up to 4 of its cars, and the number of cars in it today.
    images: list[str] = []
    car_count: int | None = None
    # The voters with their pictures. None when the choices are hidden from this user.
    voter_pictures: list["PersonOut"] | None = None


class PersonOut(Schema):
    username: str
    avatar_url: str | None


class VoterOut(Schema):
    username: str
    power: int
    voted: bool
    avatar_url: str | None = None


class TieOut(Schema):
    option_ids: list[int]
    open_slots: int


class BallotLink(Schema):
    id: int
    title: str
    status: str


class BallotSummary(Schema):
    id: int
    kind: str
    title: str
    status: str
    parent_id: int | None
    winners: list[str]
    closes_at: datetime | None
    # None when the user is not a voter of the ballot.
    voted: bool | None


class MyBallotOut(BallotSummary):
    championship: str
    season: str


class BallotDetail(Schema):
    id: int
    season_id: int
    season_name: str
    championship_id: int
    championship_name: str
    kind: str
    title: str
    status: str
    method: str
    selection_limit: int
    slots: int
    choice_visibility: str
    totals_visibility: str
    allow_vote_changes: bool
    closes_at: datetime | None
    eligible_roles: list[str]
    prior_season_id: int | None
    min_prior_starts: int
    max_runoffs: int | None
    power_exceptions: list[VoterOut]
    power_overrides: dict[str, int]  # User ID to power, set before the opening.
    choice_overrides: dict[str, int]  # User ID to the options that the user can choose.
    my_choice_limit: int
    closed_early: bool
    close_reason: str
    opens_at: datetime | None
    remind_hours_before: int
    reminded_at: datetime | None
    min_participation_pct: int
    low_participation_action: str
    low_participation: bool
    show_voter_names: bool
    excluded_track_ids: list[int]
    voted_names: list[str] | None  # Who voted, when the ballot shows names, and for admins.
    class_rounds: bool
    stage: str  # "main", "runoff", or "subclass".
    parent: BallotLink | None
    runoffs: list[BallotLink]
    subclass_rounds: list[BallotLink]
    can_manage: bool
    can_vote: bool
    my_power: int
    my_choices: list[int]
    voted_count: int
    voter_count: int
    totals_visible: bool
    choices_visible: bool
    options: list[OptionOut]
    tie: TieOut | None
    voters: list[VoterOut] | None  # Only for admins.


def _season(user, season_id: int) -> Season:
    season = get_object_or_404(Season.objects.select_related("championship"), pk=season_id)
    if not can_view(user, season.championship):
        raise Http404
    return season


def _ballot(user, ballot_id: int) -> Ballot:
    ballot = get_object_or_404(
        Ballot.objects.select_related("season__championship", "parent"), pk=ballot_id
    )
    if not can_view(user, ballot.season.championship):
        raise Http404
    return ballot


def _manager(user, ballot: Ballot) -> None:
    if not can_manage(user, ballot.season.championship):
        raise HttpError(403, "forbidden")


def _run(action):
    try:
        return action()
    except BallotError as error:
        raise HttpError(422, error.code) from error


def _link(ballot: Ballot) -> BallotLink:
    return BallotLink(id=ballot.id, title=ballot.title, status=ballot.status)


def _detail(user, ballot: Ballot) -> BallotDetail:
    manager = can_manage(user, ballot.season.championship)
    closed = ballot.status in (Ballot.State.CLOSED, Ballot.State.DECIDED)
    totals_visible = (
        manager
        or ballot.totals_visibility == Ballot.TotalsVisibility.LIVE
        or (ballot.totals_visibility == Ballot.TotalsVisibility.AFTER_CLOSE and closed)
    )
    choices_visible = manager or (
        ballot.choice_visibility == Ballot.ChoiceVisibility.VISIBLE and totals_visible
    )
    counts = totals(ballot)
    me = ballot.voters.filter(user=user).first()
    names: dict[int, list[str]] = {}
    pictures: dict[int, list[PersonOut]] = {}
    for vote in Vote.objects.filter(option__ballot=ballot).select_related("voter__user"):
        names.setdefault(vote.option_id, []).append(vote.voter.user.username)
        pictures.setdefault(vote.option_id, []).append(
            PersonOut(username=vote.voter.user.username, avatar_url=vote.voter.user.avatar_url())
        )
    voted, voter_count = voted_counts(ballot)
    tied, open_slots = tie(ballot)
    voters_with_votes = set(
        Vote.objects.filter(voter__ballot=ballot).values_list("voter_id", flat=True)
    )
    all_voters = list(ballot.voters.select_related("user"))
    class_pictures = {o.id: _class_pictures(o.car_class_id) for o in ballot.options.all()}
    return BallotDetail(
        id=ballot.id,
        season_id=ballot.season_id,
        season_name=ballot.season.name,
        championship_id=ballot.season.championship.id,
        championship_name=ballot.season.championship.name,
        kind=ballot.kind,
        title=ballot.title,
        status=ballot.status,
        method=ballot.method,
        selection_limit=ballot.selection_limit,
        slots=ballot.slots,
        choice_visibility=ballot.choice_visibility,
        totals_visibility=ballot.totals_visibility,
        allow_vote_changes=ballot.allow_vote_changes,
        closes_at=ballot.closes_at,
        eligible_roles=ballot.eligible_roles,
        prior_season_id=ballot.prior_season_id,
        min_prior_starts=ballot.min_prior_starts,
        max_runoffs=ballot.max_runoffs,
        power_overrides={str(k): int(v) for k, v in ballot.power_overrides.items()},
        choice_overrides={str(k): int(v) for k, v in ballot.choice_overrides.items()},
        my_choice_limit=choice_limit(ballot, user) if user.is_authenticated else 0,
        power_exceptions=[
            VoterOut(username=v.user.username, power=v.power, voted=v.id in voters_with_votes)
            for v in all_voters
            if v.power != 1
        ],
        closed_early=ballot.closed_early,
        close_reason=ballot.close_reason,
        opens_at=ballot.opens_at,
        remind_hours_before=ballot.remind_hours_before,
        reminded_at=ballot.reminded_at,
        min_participation_pct=ballot.min_participation_pct,
        low_participation_action=ballot.low_participation_action,
        low_participation=ballot.low_participation,
        show_voter_names=ballot.show_voter_names,
        excluded_track_ids=ballot.excluded_track_ids,
        voted_names=sorted(v.user.username for v in all_voters if v.id in voters_with_votes)
        if manager or ballot.show_voter_names
        else None,
        class_rounds=ballot.class_rounds,
        stage=ballot.stage,
        parent=_link(ballot.parent) if ballot.parent else None,
        runoffs=[_link(r) for r in ballot.runoffs.filter(stage=Ballot.Stage.RUNOFF)],
        subclass_rounds=[_link(r) for r in ballot.runoffs.filter(stage=Ballot.Stage.SUBCLASS)],
        can_manage=manager,
        can_vote=bool(me and me.power > 0 and ballot.status == Ballot.State.OPEN),
        my_power=me.power if me else 0,
        my_choices=list(me.votes.values_list("option_id", flat=True)) if me else [],
        voted_count=voted,
        voter_count=voter_count,
        totals_visible=totals_visible,
        choices_visible=choices_visible,
        options=[
            OptionOut(
                id=o.id,
                label=o.label,
                track_layout_id=o.track_layout_id,
                car_class_id=o.car_class_id,
                selected=o.selected,
                selected_by=o.selected_by,
                votes=counts[o.id] if totals_visible else None,
                voters=sorted(names.get(o.id, [])) if choices_visible else None,
                image_url=_option_image(o),
                images=class_pictures[o.id][0],
                car_count=class_pictures[o.id][1],
                voter_pictures=sorted(pictures.get(o.id, []), key=lambda p: p.username)
                if choices_visible
                else None,
            )
            for o in ballot.options.select_related("track_layout")
        ],
        tie=TieOut(option_ids=[o.id for o in tied], open_slots=open_slots) if tied else None,
        voters=[
            VoterOut(
                username=v.user.username,
                power=v.power,
                voted=v.id in voters_with_votes,
                avatar_url=v.user.avatar_url(),
            )
            for v in all_voters
        ]
        if manager
        else None,
    )


def _option_image(option) -> str | None:
    """The picture of a track option, or of the first car with a picture of a class option."""
    if option.track_layout_id:
        return option.track_layout.image_url("preview")
    pictures, _ = _class_pictures(option.car_class_id)
    return pictures[0] if pictures else None


def _class_candidate(car_class: CarClass, added: set[int]) -> "CandidateOut":
    pictures, count = _class_pictures(car_class.id)
    return CandidateOut(
        id=car_class.id,
        group=car_class.parent.name if car_class.parent_id else "",
        label=car_class.name,
        image_url=pictures[0] if pictures else None,
        images=pictures,
        car_count=count,
        status="added" if car_class.id in added else "ok",
    )


def _class_pictures(class_id: int | None) -> tuple[list[str], int | None]:
    """Up to 4 car pictures of a car class, and the number of its cars today."""
    if class_id is None:
        return [], None
    cars = list(
        Car.objects.filter(
            class_memberships__car_class_id__in=with_subclasses([class_id]),
            class_memberships__valid_to__isnull=True,
        )
        .distinct()
        .order_by("name")
    )
    pictures = [url for car in cars if (url := car.image_url("preview"))][:4]
    return pictures, len(cars)


def _settings(payload: BallotSettingsIn) -> dict:
    return payload.dict(exclude_unset=True, exclude={"kind"})


@router.get("/me/ballots", response=list[MyBallotOut])
def my_ballots(request):
    """The ballots where the user is a voter: the open ones first, then the latest closed."""
    voters = {
        voter.ballot_id: voter.id
        for voter in BallotVoter.objects.filter(user=request.user, power__gt=0)
    }
    voted = set(
        Vote.objects.filter(voter_id__in=voters.values()).values_list("voter_id", flat=True)
    )
    ballots = (
        Ballot.objects.filter(id__in=voters)
        .exclude(status=Ballot.State.DRAFT)
        .select_related("season__championship")
        .prefetch_related("options")
    )
    rows = [
        MyBallotOut(
            id=b.id,
            kind=b.kind,
            title=b.title,
            status=b.status,
            parent_id=b.parent_id,
            winners=[o.label for o in b.options.all() if o.selected]
            if b.status == Ballot.State.DECIDED
            else [],
            closes_at=b.closes_at,
            voted=voters[b.id] in voted,
            championship=b.season.championship.name,
            season=b.season.name,
        )
        for b in ballots
    ]
    rows.sort(key=lambda row: (row.status != Ballot.State.OPEN, -row.id))
    return rows[:30]


@router.get("/seasons/{season_id}/ballots", response=list[BallotSummary])
def list_ballots(request, season_id: int):
    season = _season(request.user, season_id)
    mine = {
        voter.ballot_id: voter.id
        for voter in BallotVoter.objects.filter(ballot__season=season, user=request.user)
    }
    voted = set(Vote.objects.filter(voter_id__in=mine.values()).values_list("voter_id", flat=True))
    return [
        BallotSummary(
            id=b.id,
            kind=b.kind,
            title=b.title,
            status=b.status,
            parent_id=b.parent_id,
            winners=[o.label for o in b.options.all() if o.selected]
            if b.status == Ballot.State.DECIDED
            else [],
            closes_at=b.closes_at,
            voted=mine[b.id] in voted if b.id in mine else None,
        )
        for b in season.ballots.prefetch_related("options")
    ]


@router.post("/seasons/{season_id}/ballots", response={201: BallotDetail})
def create(request, season_id: int, payload: BallotIn):
    season = _season(request.user, season_id)
    if not can_manage(request.user, season.championship):
        raise HttpError(403, "forbidden")
    ballot = _run(lambda: create_ballot(season, request.user, payload.kind, _settings(payload)))
    return Status(201, _detail(request.user, ballot))


@router.get("/ballots/{ballot_id}", response=BallotDetail)
def get_ballot(request, ballot_id: int):
    return _detail(request.user, _ballot(request.user, ballot_id))


@router.patch("/ballots/{ballot_id}", response=BallotDetail)
def update(request, ballot_id: int, payload: BallotSettingsIn):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: update_ballot(ballot, request.user, _settings(payload)))
    return _detail(request.user, ballot)


class CandidateOut(Schema):
    id: int  # The layout ID (track ballot) or the car class ID (car class ballot).
    group: str  # The track name, or "" for a car class.
    label: str
    image_url: str | None = None
    images: list[str] = []  # A car class: up to 4 car pictures.
    car_count: int | None = None
    # "ok", "added", "track_excluded", "layout_is_fixed", or "grid_too_small".
    status: str


@router.get("/ballots/{ballot_id}/candidates", response=list[CandidateOut])
def candidates(request, ballot_id: int):
    """Every layout or car class of the catalog, with its state for this ballot."""
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    if ballot.kind == Ballot.Kind.TRACK:
        added = set(ballot.options.values_list("track_layout_id", flat=True))
        fixed = fixed_layout_ids(ballot.season)
        drivers = ballot.season.entries.count()
        layouts = TrackLayout.objects.select_related("track").order_by("track__name", "name")
        return [
            CandidateOut(
                id=layout.id,
                group=layout.track.name,
                label=layout.name,
                image_url=layout.image_url("preview"),
                status="added"
                if layout.id in added
                else layout_problem(ballot, layout, fixed, drivers) or "ok",
            )
            for layout in layouts
        ]
    added = set(ballot.options.values_list("car_class_id", flat=True))
    classes = CarClass.objects.select_related("parent")
    if ballot.class_rounds:
        classes = classes.filter(parent__isnull=True)  # The subclasses come in the 2nd round.
    # A class, then its subclasses.
    rows = sorted(
        classes, key=lambda c: (c.parent.name if c.parent_id else c.name, c.parent_id or 0, c.name)
    )
    return [_class_candidate(c, added) for c in rows]


class OptionCarOut(Schema):
    id: int
    name: str
    brand: str
    year: int | None
    image_url: str | None


class CarGroupOut(Schema):
    # None: the cars of the class itself. Else the name of a subclass.
    subclass: str | None
    cars: list[OptionCarOut]


@router.get("/ballots/{ballot_id}/options/{option_id}/cars", response=list[CarGroupOut])
def option_cars(request, ballot_id: int, option_id: int):
    """Every car of a car class option today: the cars of the class, then the cars of each
    subclass. Each person who can see the ballot can see them."""
    ballot = _ballot(request.user, ballot_id)
    option = get_object_or_404(ballot.options.select_related("car_class"), pk=option_id)
    if option.car_class is None:
        return []
    classes = [option.car_class, *option.car_class.subclasses.order_by("name")]
    groups = []
    for car_class in classes:
        cars = Car.objects.filter(
            class_memberships__car_class=car_class, class_memberships__valid_to__isnull=True
        ).order_by("name")
        rows = [
            OptionCarOut(
                id=car.id,
                name=car.name,
                brand=car.brand,
                year=car.year,
                image_url=car.image_url("preview"),
            )
            for car in cars.distinct()
        ]
        if rows:
            subclass = None if car_class.id == option.car_class_id else car_class.name
            groups.append(CarGroupOut(subclass=subclass, cars=rows))
    return groups


class SetOptionsIn(Schema):
    ids: list[int] = Field(max_length=500)


@router.put("/ballots/{ballot_id}/options", response=BallotDetail)
def put_options(request, ballot_id: int, payload: SetOptionsIn):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: set_options(ballot, request.user, payload.ids))
    return _detail(request.user, ballot)


@router.post("/ballots/{ballot_id}/options", response=BallotDetail)
def create_option(request, ballot_id: int, payload: OptionIn):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(
        lambda: add_option(
            ballot,
            request.user,
            label=payload.label,
            layout_id=payload.track_layout_id,
            car_class_id=payload.car_class_id,
        )
    )
    return _detail(request.user, ballot)


@router.delete("/ballots/{ballot_id}/options/{option_id}", response=BallotDetail)
def delete_option(request, ballot_id: int, option_id: int):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    option = get_object_or_404(BallotOption, pk=option_id, ballot=ballot)
    _run(lambda: remove_option(option, request.user))
    return _detail(request.user, ballot)


@router.post("/ballots/{ballot_id}/open", response=BallotDetail)
def open_(request, ballot_id: int):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: open_ballot(ballot, request.user))
    return _detail(request.user, ballot)


@router.put("/ballots/{ballot_id}/vote", response=BallotDetail)
def vote(request, ballot_id: int, payload: VoteIn):
    ballot = _ballot(request.user, ballot_id)
    _run(lambda: cast_vote(ballot, request.user, payload.option_ids))
    return _detail(request.user, ballot)


@router.post("/ballots/{ballot_id}/close", response=BallotDetail)
def close(request, ballot_id: int, payload: CloseIn):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: close_ballot(ballot, request.user, reason=payload.reason))
    ballot.refresh_from_db()
    return _detail(request.user, ballot)


@router.post("/ballots/{ballot_id}/remind", response=BallotDetail)
def remind_now(request, ballot_id: int):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: remind(ballot, request.user))
    ballot.refresh_from_db()
    return _detail(request.user, ballot)


@router.post("/ballots/{ballot_id}/runoff", response=BallotDetail)
def runoff(request, ballot_id: int):
    """Start a runoff. The answer is the new runoff ballot."""
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    new = _run(lambda: start_runoff(ballot, request.user))
    return _detail(request.user, new)


@router.post("/ballots/{ballot_id}/decide", response=BallotDetail)
def decide(request, ballot_id: int, payload: DecideIn):
    ballot = _ballot(request.user, ballot_id)
    _manager(request.user, ballot)
    _run(lambda: decide_manually(ballot, request.user, payload.option_ids, payload.reason))
    ballot.refresh_from_db()
    return _detail(request.user, ballot)
