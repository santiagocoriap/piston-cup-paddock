from django.contrib import admin
from django.urls import path, re_path

from apps.core.views import frontend

from .api import api

urlpatterns = [
    path("api/", api.urls),
    path("django-admin/", admin.site.urls),
    re_path(r"^(?!api/|django-admin/|static/).*$", frontend),
]
