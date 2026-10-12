from django.conf import settings
from django.http import HttpResponse


def frontend(request, path=""):
    """Serve the React app. React handles every path that is not /api, /admin, or /static."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse("The frontend build is missing.", status=503, content_type="text/plain")
    return HttpResponse(index.read_text(encoding="utf-8"))
