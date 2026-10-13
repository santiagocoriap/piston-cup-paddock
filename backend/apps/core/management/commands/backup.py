from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.backup import create_backup, run_backup
from apps.core.models import BackupRun


class Command(BaseCommand):
    help = "Back up the database and the stored files into one zip file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="The zip file to write. Default: backups/paddock-<date>.zip",
        )

    def handle(self, *args, output, **options):
        if output is None:
            run = BackupRun.objects.create()
            run_backup(run)
            if run.status == BackupRun.Status.FAILED:
                raise CommandError(f"The backup failed: {run.error}")
            message = (
                f"Backup written to backups/{run.file_name}: {run.rows} rows, {run.files} files."
            )
            self.stdout.write(self.style.SUCCESS(message))
            return
        path = Path(output)
        manifest = create_backup(path)
        rows = sum(manifest["rows"].values())
        files = len(manifest["files"])
        self.stdout.write(
            self.style.SUCCESS(f"Backup written to {path}: {rows} rows, {files} files.")
        )
