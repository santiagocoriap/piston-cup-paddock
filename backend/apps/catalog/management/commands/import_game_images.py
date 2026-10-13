from django.core.management.base import BaseCommand, CommandError

from apps.catalog.game_images import GameImagesError, import_game_images, open_source


class Command(BaseCommand):
    help = (
        "Copy track maps, track pictures and car pictures from the Assetto Corsa content "
        "folder (or a ZIP made by tools/pack_game_images.py) into the catalog."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="The assettocorsa folder, its content folder, or a ZIP.")

    def handle(self, *args, path, **options):
        try:
            report = import_game_images(open_source(path))
        except GameImagesError as error:
            raise CommandError(error.code) from error
        self.stdout.write(f"Layouts with images: {len(report.layouts)}")
        self.stdout.write(f"Cars with images: {len(report.cars)}")
        for label in report.missing_layouts:
            self.stdout.write(f"  No files for layout {label}")
        for key in report.missing_cars:
            self.stdout.write(f"  No files for car {key}")
        self.stdout.write(self.style.SUCCESS("Done."))
