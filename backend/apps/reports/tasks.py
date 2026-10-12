from procrastinate.contrib.django import app

from .services import generate


@app.task(name="reports.generate")
def generate_report(report_id: int) -> str:
    """Write the text of one report. LiteLLM retries the provider call two times."""
    return generate(report_id).status
