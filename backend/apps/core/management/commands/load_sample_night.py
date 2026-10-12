"""Load the sanitized race night of samples/ as a demo championship.

The command uses the same import steps as an admin on the round page: the qualifying file,
the race file, and the Real Penalty logs. The result stays provisional.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Car, Track, TrackLayout
from apps.competition.models import Championship, League, Round, Season, SeasonEntry
from apps.identity.models import DriverProfile, User
from apps.imports import penalty_services, services
from apps.imports.ac_results import parse

NIGHT = "2026-10-11-ks-highlands"
FILES = ["2026_10_11_18_54_QUALIFY.json", "2026_10_11_20_7_RACE.json"]
CHAMPIONSHIP = "Demo LMDh"


class Command(BaseCommand):
    help = "Load the sample race night of 2026-10-11 at Highlands as a demo championship."

    def add_arguments(self, parser):
        default = settings.BASE_DIR.parent / "samples" / NIGHT
        parser.add_argument("--folder", type=Path, default=default)
        parser.add_argument(
            "--reset", action="store_true", help="Delete the demo championship first."
        )

    def handle(self, *args, folder: Path, reset: bool, **options):
        if not (folder / FILES[1]).exists():
            raise CommandError(f"No sample files in {folder}")
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if user is None:
            raise CommandError("Create the first admin before you load the sample.")
        existing = Championship.objects.filter(name=CHAMPIONSHIP).first()
        if existing and not reset:
            raise CommandError(f'"{CHAMPIONSHIP}" exists. Use --reset to load it again.')
        if existing:
            self._delete(existing)

        files = {name: (folder / name).read_bytes() for name in FILES}
        round_ = self._setup(files)
        for name in FILES:
            item, _ = services.upload(round_, name, files[name], user)
            services.apply(item, user, statuses={}, ignored=[])
        for path in sorted((folder / "realpenalty").glob("*.log")):
            penalty_services.upload_log(round_, path.name, path.read_bytes(), user)
        view = penalty_services.preview(round_)
        served = [p.key for p in view.penalties if p.kind == "served" and p.entry_id]
        penalty_services.apply(round_, user, penalty_keys=served)

        self.stdout.write(
            self.style.SUCCESS(f"Loaded {CHAMPIONSHIP}. Open /rounds/{round_.id} in the app.")
        )

    @transaction.atomic
    def _setup(self, files: dict[str, bytes]) -> Round:
        league = League.objects.order_by("id").first() or League.objects.create(name="Piston Cup")
        championship = Championship.objects.create(league=league, name=CHAMPIONSHIP)
        season = Season.objects.create(
            championship=championship, name="2026", planned_round_count=8
        )
        drivers = {}
        for content in files.values():
            for driver in parse(json.loads(content)).drivers:
                drivers.setdefault(driver.guid, driver)
        first = parse(json.loads(files[FILES[1]]))
        track, _ = Track.objects.get_or_create(key=first.track, defaults={"name": "Highlands"})
        layout, _ = TrackLayout.objects.get_or_create(
            track=track, key=first.layout, defaults={"name": "Long"}
        )
        for number, driver in enumerate(drivers.values(), start=1):
            car, _ = Car.objects.get_or_create(
                key=driver.car_model.lower(), defaults={"name": driver.car_model}
            )
            profile, _ = DriverProfile.objects.get_or_create(
                steam_guid=driver.guid, defaults={"display_name": driver.name}
            )
            SeasonEntry.objects.create(season=season, driver=profile, car=car, number=number)
        tz = ZoneInfo(league.timezone)
        return Round.objects.create(
            season=season,
            number=1,
            track_layout=layout,
            scheduled_at=datetime(2026, 10, 11, 19, 0, tzinfo=tz),
        )

    @transaction.atomic
    def _delete(self, championship: Championship) -> None:
        # Seasons and entries use PROTECT, so delete from the bottom up.
        for season in championship.seasons.all():
            season.rounds.all().delete()
            season.entries.all().delete()
            season.delete()
        championship.delete()
