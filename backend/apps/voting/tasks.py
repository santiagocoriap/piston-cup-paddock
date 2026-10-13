from procrastinate.contrib.django import app

from .services import run_schedule


@app.periodic(cron="* * * * *")
@app.task(name="voting.schedule", queueing_lock="voting.schedule")
def schedule(timestamp: int) -> dict:
    """Open, remind, and close ballots on time."""
    return run_schedule()
