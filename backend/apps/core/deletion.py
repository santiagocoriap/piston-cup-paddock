"""Delete leagues, championships, seasons, races, and the other things of the app.

Two kinds of delete:

- A container (league, championship, season, race, entry, vote) goes with everything inside
  it: its seasons, races, results, laps, and so on. The page asks the admin to confirm first.
- A shared thing (track, layout, car, car class, driver) stays while a race, an entry, a record,
  or a vote uses it, so the race history never breaks. The error says where it is in use.

A user goes, and their driver profile stays without an account. A league admin cannot delete
their own account or the last league admin.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.audit.services import record
from apps.catalog.models import Car, CarClass, Track, TrackLayout
from apps.competition.models import (
    Championship,
    ChampionshipMember,
    League,
    Round,
    RoundTrackChange,
    Season,
    SeasonEntry,
)
from apps.competition.permissions import can_manage, is_league_admin
from apps.identity.models import DriverProfile
from apps.records.models import ManualRecord
from apps.results.models import Penalty, ResultLine
from apps.voting.models import Ballot, BallotOption

KINDS = (
    "league",
    "championship",
    "season",
    "round",
    "entry",
    "ballot",
    "driver",
    "user",
    "track",
    "layout",
    "car",
    "car_class",
)


class DeleteError(Exception):
    def __init__(self, code: str, uses: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.uses = uses or []


# Containers: each one deletes what is inside it first, because some links block a delete.


def _delete_round(round_: Round) -> None:
    round_.delete()  # Results, imports, laps, and reports of the race go with it.


def _delete_season(season: Season) -> None:
    for round_ in season.rounds.all():
        _delete_round(round_)
    # The entries go after the races: a result line keeps its entry.
    season.entries.all().delete()
    season.delete()


def _delete_championship(championship: Championship) -> None:
    for season in championship.seasons.all():
        _delete_season(season)
    # A member keeps its custom role, so the members go before the roles.
    ChampionshipMember.objects.filter(championship=championship).delete()
    championship.delete()


def _delete_league(league: League) -> None:
    for championship in league.championships.all():
        _delete_championship(championship)
    league.delete()


def _delete_entry(entry: SeasonEntry) -> None:
    lines = ResultLine.objects.filter(entry=entry).count()
    penalties = Penalty.objects.filter(entry=entry).count()
    if lines or penalties:
        raise DeleteError("entry_has_results", [f"results:{lines}", f"penalties:{penalties}"])
    entry.delete()


# Shared things: they stay while something uses them.


def _layout_uses(layouts) -> list[str]:
    uses = []
    rounds = Round.objects.filter(track_layout__in=layouts).select_related("season__championship")
    uses += [f"round:{r.season.championship.name} {r.season.name} R{r.number}" for r in rounds[:5]]
    changes = RoundTrackChange.objects.filter(Q(old_layout__in=layouts) | Q(new_layout__in=layouts))
    if changes.exists():
        uses.append(f"track_changes:{changes.count()}")
    records = ManualRecord.objects.filter(layout__in=layouts).count()
    if records:
        uses.append(f"records:{records}")
    options = BallotOption.objects.filter(track_layout__in=layouts).select_related("ballot")
    uses += [f"ballot:{o.ballot.title}" for o in options[:5]]
    return uses


def _delete_layout(layout: TrackLayout) -> None:
    uses = _layout_uses([layout])
    if uses:
        raise DeleteError("in_use", uses)
    layout.delete()


def _delete_track(track: Track) -> None:
    uses = _layout_uses(list(track.layouts.all()))
    if uses:
        raise DeleteError("in_use", uses)
    track.layouts.all().delete()
    track.delete()


def _delete_car(car: Car) -> None:
    entries = SeasonEntry.objects.filter(car=car).select_related("season", "driver")
    uses = [f"entry:{e.season.name} · {e.driver.display_name}" for e in entries[:5]]
    records = ManualRecord.objects.filter(car=car).count()
    if records:
        uses.append(f"records:{records}")
    if uses:
        raise DeleteError("in_use", uses)
    car.delete()


def _delete_car_class(car_class: CarClass) -> None:
    options = BallotOption.objects.filter(car_class=car_class).select_related("ballot")
    uses = [f"ballot:{o.ballot.title}" for o in options[:5]]
    if uses:
        raise DeleteError("in_use", uses)
    car_class.delete()


def _delete_driver(driver: DriverProfile) -> None:
    entries = SeasonEntry.objects.filter(driver=driver).select_related("season")
    uses = [f"entry:{e.season.name} #{e.number}" for e in entries[:5]]
    if uses:
        raise DeleteError("in_use", uses)
    driver.delete()


def _delete_user(user, actor) -> None:
    if user.pk == actor.pk:
        raise DeleteError("delete_self")
    if (
        user.is_staff
        and not get_user_model().objects.filter(is_staff=True).exclude(pk=user.pk).exists()
    ):
        raise DeleteError("last_admin")
    user.delete()  # The driver profile stays, without an account.


def _target(kind: str, object_id: int):
    models = {
        "league": League,
        "championship": Championship,
        "season": Season,
        "round": Round,
        "entry": SeasonEntry,
        "ballot": Ballot,
        "driver": DriverProfile,
        "user": get_user_model(),
        "track": Track,
        "layout": TrackLayout,
        "car": Car,
        "car_class": CarClass,
    }
    model = models.get(kind)
    if model is None:
        raise DeleteError("unknown_kind")
    found = model.objects.filter(pk=object_id).first()
    if found is None:
        raise DeleteError("not_found")
    return found


def _championship_of(kind: str, target) -> Championship | None:
    if kind == "championship":
        return target
    if kind == "season":
        return target.championship
    if kind in ("round", "entry", "ballot"):
        return target.season.championship
    return None


def can_delete(user, kind: str, target) -> bool:
    """A league admin can delete all. A championship admin can delete the seasons, races,
    entries, and votes of their championship."""
    if is_league_admin(user):
        return True
    championship = _championship_of(kind, target)
    return championship is not None and kind != "championship" and can_manage(user, championship)


def delete(kind: str, object_id: int, user) -> str:
    """Delete one thing. Gives its name, for the message of the page."""
    target = _target(kind, object_id)
    if not can_delete(user, kind, target):
        raise DeleteError("forbidden")
    name = str(target)
    championship = _championship_of(kind, target)
    with transaction.atomic():
        if kind == "league":
            _delete_league(target)
        elif kind == "championship":
            _delete_championship(target)
        elif kind == "season":
            _delete_season(target)
        elif kind == "round":
            _delete_round(target)
        elif kind == "entry":
            _delete_entry(target)
        elif kind == "ballot":
            target.delete()
        elif kind == "driver":
            _delete_driver(target)
        elif kind == "user":
            _delete_user(target, user)
        elif kind == "track":
            _delete_track(target)
        elif kind == "layout":
            _delete_layout(target)
        elif kind == "car":
            _delete_car(target)
        elif kind == "car_class":
            _delete_car_class(target)
        # The log entry outlives the thing: it keeps no link to a deleted championship.
        keep = championship if kind in ("round", "entry", "ballot", "season") else None
        if keep is not None and not Championship.objects.filter(pk=keep.pk).exists():
            keep = None
        record(user, f"{kind}.deleted", kind, object_id, championship=keep, params={"name": name})
    return name
