import logging

from procrastinate.contrib.django import app

logger = logging.getLogger(__name__)


@app.task(name="core.ping")
def ping() -> str:
    """Prove that the worker runs tasks."""
    logger.info("pong")
    return "pong"


@app.task(name="core.backup")
def backup(run_id: int) -> None:
    """Do a backup that an admin started from the page."""
    from .backup import run_backup
    from .models import BackupRun

    run = BackupRun.objects.filter(pk=run_id, status=BackupRun.Status.RUNNING).first()
    if run is not None:
        run_backup(run)
