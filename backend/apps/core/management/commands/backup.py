from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.core.backup import create_backup


class Command(BaseCommand):
    help = "Back up the database and the stored files into one zip file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="The zip file to write. Default: backups/paddock-<date>.zip",
        )

    def handle(self, *args, output, **options):
        if output is None:
            output = f"backups/paddock-{datetime.now():%Y%m%d-%H%M%S}.zip"
        path = Path(output)
        manifest = create_backup(path)
        rows = sum(manifest["rows"].values())
        files = len(manifest["files"])
        self.stdout.write(
            self.style.SUCCESS(f"Backup written to {path}: {rows} rows, {files} files.")
        )
