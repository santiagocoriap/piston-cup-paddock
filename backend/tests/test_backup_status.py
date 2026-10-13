"""Backup status on the health card and the backup button. League admins only."""

import json
import zipfile

import pytest
from django.core import management
from django.db import connection

from apps.core.backup import run_backup
from apps.core.models import BackupRun


@pytest.fixture(autouse=True)
def folders(settings, tmp_path):
    settings.BACKUP_ROOT = tmp_path / "backups"
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def admin(make_user):
    return make_user("admin", is_staff=True, is_superuser=True)


def test_status_is_empty_before_the_first_backup(api, admin):
    assert api(admin).get("/backups/status").json() == {"last": None, "last_ok_at": None}


def test_admin_starts_a_backup_and_the_worker_does_it(api, admin, settings):
    response = api(admin).post("/backups").json()
    assert response["last"]["status"] == "running"
    assert response["last"]["started_by"] == admin.username
    with connection.cursor() as cursor:
        cursor.execute("SELECT task_name, args FROM procrastinate_jobs ORDER BY id DESC LIMIT 1")
        name, args = cursor.fetchone()
    assert name == "core.backup"
    # A second click while the first backup runs does nothing.
    assert api(admin).post("/backups").json()["detail"] == "backup_running"

    run_id = (json.loads(args) if isinstance(args, str) else args)["run_id"]
    run_backup(BackupRun.objects.get(pk=run_id))
    last = api(admin).get("/backups/status").json()
    assert last["last"]["status"] == "ok" and last["last_ok_at"] is not None
    assert last["last"]["size_bytes"] > 0 and last["last"]["rows"] > 0
    path = settings.BACKUP_ROOT / last["last"]["file_name"]
    with zipfile.ZipFile(path) as archive:
        assert "core.backuprun" not in archive.read("data.json").decode()


def test_a_failed_backup_shows_the_error(api, admin, monkeypatch):
    def broken(output):
        raise OSError("No space left on device")

    monkeypatch.setattr("apps.core.backup.create_backup", broken)
    run = BackupRun.objects.create(started_by=admin)
    run_backup(run)
    last = api(admin).get("/backups/status").json()
    assert last["last"]["status"] == "failed"
    assert last["last"]["error"] == "No space left on device"
    assert last["last_ok_at"] is None


def test_the_command_also_records_the_run(db, settings):
    management.call_command("backup")
    run = BackupRun.objects.get()
    assert run.status == "ok" and (settings.BACKUP_ROOT / run.file_name).exists()


def test_only_a_league_admin_sees_backups(api, champ_admin):
    assert api(champ_admin).get("/backups/status").status_code == 403
    assert api(champ_admin).post("/backups").status_code == 403
