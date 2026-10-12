from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.backup import BackupError, restore_backup


class Command(BaseCommand):
    help = (
        "Replace ALL data and stored files with a backup zip file. This deletes the current data."
    )

    def add_arguments(self, parser):
        parser.add_argument("file", help="The backup zip file.")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required. Confirms that the current data will be deleted.",
        )

    def handle(self, *args, file, confirm, **options):
        if not confirm:
            raise CommandError(
                "Restore deletes all current data. Run the command again with --confirm."
            )
        path = Path(file)
        if not path.exists():
            raise CommandError(f"The file {path} does not exist.")
        try:
            manifest = restore_backup(path)
        except BackupError as error:
            raise CommandError(str(error)) from error
        rows = sum(manifest["rows"].values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Restored the backup of {manifest['created_at']}: {rows} rows, "
                f"{len(manifest['files'])} files. Users must sign in again."
            )
        )
