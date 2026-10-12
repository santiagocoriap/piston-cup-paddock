from ninja import NinjaAPI
from ninja.security import django_auth

from apps.catalog.api import router as catalog_router
from apps.competition.api import router as competition_router
from apps.core.api import router as core_router
from apps.identity.api import router as auth_router
from apps.identity.drivers_api import router as drivers_router

# Every endpoint needs a signed-in user, unless it sets auth=None.
api = NinjaAPI(title="Piston Cup Paddock", version="0.1.0", urls_namespace="api", auth=django_auth)
api.add_router("/", core_router)
api.add_router("/auth", auth_router)
api.add_router("/catalog", catalog_router)
api.add_router("/", drivers_router)
api.add_router("/", competition_router)
