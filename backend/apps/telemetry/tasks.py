from procrastinate.contrib.django import app

from .coach import write


@app.task(name="telemetry.engineer_note")
def write_note(note_id: int) -> str:
    """Write one coaching note of the race engineer. LiteLLM retries the call two times."""
    return write(note_id).status
