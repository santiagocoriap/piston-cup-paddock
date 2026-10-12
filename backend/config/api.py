from ninja import NinjaAPI

from apps.core.api import router as core_router
from apps.identity.api import router as auth_router

api = NinjaAPI(title="Piston Cup Paddock", version="0.1.0", urls_namespace="api")
api.add_router("/", core_router)
api.add_router("/auth", auth_router)
