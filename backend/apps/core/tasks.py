import logging

from procrastinate.contrib.django import app

logger = logging.getLogger(__name__)


@app.task(name="core.ping")
def ping() -> str:
    """Prove that the worker runs tasks."""
    logger.info("pong")
    return "pong"
