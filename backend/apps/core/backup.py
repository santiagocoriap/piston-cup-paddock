"""Back up and restore the whole league: the database and the stored files, in one zip file.

The zip file holds:
- data.json: all league data, from `dumpdata`.
- media/...: the uploaded files, for example the result files that are the evidence.
- manifest.json: the date and the number of rows, to check a restore.

Login sessions, background tasks, and Django-made tables (content types, permissions) stay out.
`migrate` makes these tables again.
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import management
from django.db import transaction
from django.utils import timezone

EXCLUDED = [
    "contenttypes",
    "auth.permission",
    "sessions",
    "admin.logentry",
    "procrastinate",
    "core.backuprun",
]
FORMAT_VERSION = 1


class BackupError(ValueError):
    pass


def _counts() -> dict[str, int]:
    labels = {"audit", "catalog", "competition", "handicaps", "identity", "imports", "restarts"}
    labels |= {"results", "rules", "voting"}
    return {
        model._meta.label: model.objects.count()
        for model in apps.get_models()
        if model._meta.app_label in labels
    }


def create_backup(output: Path) -> dict:
    """Write the backup zip file and give back its manifest."""
    data = io.StringIO()
    management.call_command(
        "dumpdata",
        exclude=EXCLUDED,
        natural_foreign=True,
        indent=None,
        stdout=data,
    )
    manifest = {
        "format": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "rows": _counts(),
        "files": [],
    }
    media = Path(settings.MEDIA_ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", data.getvalue())
        if media.exists():
            for path in sorted(media.rglob("*")):
                if path.is_file() and output.resolve() != path.resolve():
                    name = path.relative_to(media).as_posix()
                    archive.write(path, f"media/{name}")
                    manifest["files"].append(name)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def restore_backup(source: Path) -> dict:
    """Replace all league data and stored files with the backup. This deletes the current data."""
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if not {"data.json", "manifest.json"} <= names:
            raise BackupError("The file is not a Piston Cup Paddock backup.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT_VERSION:
            raise BackupError("The backup format is not supported.")
        data = archive.read("data.json")

        media = Path(settings.MEDIA_ROOT).resolve()
        with transaction.atomic():
            management.call_command("flush", interactive=False, verbosity=0)
            fixture = media.parent / ".restore-data.json"
            fixture.write_bytes(data)
            try:
                management.call_command("loaddata", str(fixture), verbosity=0)
            finally:
                fixture.unlink(missing_ok=True)

        for name in manifest["files"]:
            target = (media / name).resolve()
            if media not in target.parents:
                raise BackupError(f"Unsafe file path in the backup: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(f"media/{name}"))

    if _counts() != manifest["rows"]:
        raise BackupError("The restored row counts differ from the backup.")
    return manifest


def backup_dir() -> Path:
    return Path(settings.BACKUP_ROOT)


def run_backup(run) -> None:
    """Do the backup of one run record, and write the result into the record."""
    path = backup_dir() / f"paddock-{run.started_at:%Y%m%d-%H%M%S}.zip"
    try:
        manifest = create_backup(path)
    except Exception as error:  # The card shows any failure. The admin needs the message.
        run.status = run.Status.FAILED
        run.error = str(error)[:1000] or error.__class__.__name__
        path.unlink(missing_ok=True)
    else:
        run.status = run.Status.OK
        run.file_name = path.name
        run.size_bytes = path.stat().st_size
        run.rows = sum(manifest["rows"].values())
        run.files = len(manifest["files"])
    run.finished_at = timezone.now()
    run.save()
