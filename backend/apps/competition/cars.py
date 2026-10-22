"""The cars that a season allows. A season with car classes allows only the cars in those classes
today. A season with no class allows every car. A decided car class vote sets the classes, and
the voters who have no entry yet get one, with a random car of the class."""

import random

from django.db import transaction
from django.db.models import QuerySet
from ninja.errors import HttpError

from apps.audit.services import change, record
from apps.catalog.models import Car, with_subclasses

from .models import Season, SeasonEntry


def allowed_cars(season: Season) -> QuerySet[Car]:
    """The cars of the classes of the season today, or every car for a season with no class."""
    class_ids = list(season.car_classes.values_list("id", flat=True))
    if not class_ids:
        return Car.objects.all()
    class_ids = with_subclasses(class_ids)
    return Car.objects.filter(
        class_memberships__car_class_id__in=class_ids,
        class_memberships__valid_to__isnull=True,
    ).distinct()


def allowed_car_ids(season: Season) -> list[int] | None:
    """The IDs of allowed_cars, or None when the season allows every car."""
    if not season.car_classes.exists():
        return None
    return sorted(allowed_cars(season).values_list("id", flat=True))


def require_allowed(season: Season, car: Car) -> None:
    if not allowed_cars(season).filter(pk=car.pk).exists():
        raise HttpError(422, "car_not_in_class")


def free_number(season: Season) -> int:
    """The lowest race number that no entry of the season uses."""
    taken = set(season.entries.values_list("number", flat=True))
    number = 1
    while number in taken:
        number += 1
    return number


def enter_voters(season: Season, user_ids: list[int], actor) -> list[SeasonEntry]:
    """An entry for each of these users with a driver profile and no entry in the season. The car
    is a random allowed car: the driver can change it later."""
    from apps.community.services import notify
    from apps.identity.models import DriverProfile

    cars = list(allowed_cars(season))
    if not cars:
        return []
    entered = set(season.entries.values_list("driver_id", flat=True))
    profiles = DriverProfile.objects.filter(user_id__in=user_ids).exclude(pk__in=entered)
    made = []
    with transaction.atomic():
        for profile in profiles.order_by("display_name"):
            car = random.choice(cars)
            entry = SeasonEntry.objects.create(
                season=season, driver=profile, car=car, number=free_number(season)
            )
            made.append(entry)
            record(
                actor,
                "entry.auto_created",
                "season",
                season.id,
                championship=season.championship,
                params={
                    "season": season.name,
                    "driver": profile.display_name,
                    "number": entry.number,
                    "car": car.name,
                },
                changes=[change("car", None, car.name)],
            )
            notify(
                [profile.user_id],
                "entry.auto_created",
                {"season": season.name, "car": car.name, "number": entry.number},
                f"/seasons/{season.id}#entries",
            )
    return made


def give_missing_cars(season: Season, actor) -> list[SeasonEntry]:
    """An entry with no car gets a random allowed car, for example after the car class vote.
    The driver can change it later."""
    from apps.community.services import notify

    cars = list(allowed_cars(season))
    if not cars:
        return []
    given = []
    with transaction.atomic():
        for entry in season.entries.filter(car__isnull=True).select_related("driver"):
            entry.car = random.choice(cars)
            entry.save(update_fields=["car"])
            given.append(entry)
            record(
                actor,
                "entry.car_changed",
                "season",
                season.id,
                championship=season.championship,
                params={"season": season.name, "driver": entry.driver.display_name},
                changes=[change("car", None, entry.car.name)],
            )
            if entry.driver.user_id:
                notify(
                    [entry.driver.user_id],
                    "entry.auto_created",
                    {"season": season.name, "car": entry.car.name, "number": entry.number},
                    f"/seasons/{season.id}#entries",
                )
    return given
