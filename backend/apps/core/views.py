from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_cache_control


def frontend(request, path=""):
    """Serve the React app. React handles every path that is not /api, /admin, or /static."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse("The frontend build is missing.", status=503, content_type="text/plain")
    response = HttpResponse(index.read_text(encoding="utf-8"))
    # index.html names the current bundle files. The bundle files have a hash in the name, so
    # they can stay in the cache. This page must never be reused without asking the server.
    patch_cache_control(response, no_cache=True)
    return response
