from ninja import NinjaAPI
from ninja.security import django_auth

from apps.audit.api import router as audit_router
from apps.catalog.api import router as catalog_router
from apps.collectors.api import router as collectors_router
from apps.collectors.health_api import router as health_router
from apps.collectors.incident_api import router as incidents_router
from apps.collectors.replay_api import router as replay_router
from apps.collectors.safety_api import router as safety_router
from apps.collectors.server_setup_api import router as server_setup_router
from apps.community.api import router as community_router
from apps.competition.api import router as competition_router
from apps.core.api import router as core_router
from apps.core.backup_api import router as backup_router
from apps.core.deletion_api import router as deletion_router
from apps.core.exports import router as exports_router
from apps.dashboard.api import router as dashboard_router
from apps.handicaps.api import router as handicaps_router
from apps.identity.accounts_api import router as accounts_router
from apps.identity.api import router as auth_router
from apps.identity.drivers_api import router as drivers_router
from apps.imports.api import router as imports_router
from apps.records.api import router as records_router
from apps.reports.api import router as reports_router
from apps.restarts.api import router as restarts_router
from apps.results.api import router as results_router
from apps.rules.api import router as rules_router
from apps.telemetry.api import router as telemetry_router
from apps.telemetry.script_api import router as script_router
from apps.voting.api import router as voting_router

# Every endpoint needs a signed-in user, unless it sets auth=None.
api = NinjaAPI(title="Piston Cup Paddock", version="0.1.0", urls_namespace="api", auth=django_auth)
api.add_router("/", core_router)
api.add_router("/", backup_router)
api.add_router("/", deletion_router)
api.add_router("/auth", auth_router)
api.add_router("/catalog", catalog_router)
api.add_router("/", drivers_router)
api.add_router("/", competition_router)
api.add_router("/", results_router)
api.add_router("/", audit_router)
api.add_router("/", restarts_router)
api.add_router("/", imports_router)
api.add_router("/", handicaps_router)
api.add_router("/", records_router)
api.add_router("/", voting_router)
api.add_router("/", dashboard_router)
api.add_router("/", exports_router)
api.add_router("/", accounts_router)
api.add_router("/", reports_router)
api.add_router("/", collectors_router)
api.add_router("/", telemetry_router)
api.add_router("/", health_router)
api.add_router("/", incidents_router)
api.add_router("/", safety_router)
api.add_router("/", replay_router)
api.add_router("/", rules_router)
api.add_router("/", community_router)
api.add_router("/", script_router)
api.add_router("/", server_setup_router)
