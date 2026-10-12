from django.db import connection
from ninja import Router, Schema, Status

router = Router(tags=["core"])


class Health(Schema):
    status: str
    database: bool


@router.get("/health", response={200: Health, 503: Health}, auth=None)
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return Status(503, Health(status="error", database=False))
    return Status(200, Health(status="ok", database=True))
