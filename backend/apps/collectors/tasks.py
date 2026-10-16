from procrastinate.contrib.django import app

from .alerts import check_missing_results


@app.periodic(cron="*/15 * * * *")
@app.task(name="collectors.no_results", queueing_lock="collectors.no_results")
def no_results(timestamp: int) -> int:
    """Alert the admins when a race has no result file three hours after its start."""
    return check_missing_results()
