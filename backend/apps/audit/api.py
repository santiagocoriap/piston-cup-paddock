from datetime import datetime

from ninja import Router, Schema

from apps.common.api import require
from apps.competition.models import ChampionshipMember
from apps.competition.permissions import is_league_admin

from .models import AuditEntry

router = Router(tags=["audit"])


class AuditChange(Schema):
    field: str
    old: str | int | float | bool | dict | None
    new: str | int | float | bool | dict | None


class AuditEntryOut(Schema):
    id: int
    created_at: datetime
    actor_name: str
    action: str
    championship_id: int | None
    championship_name: str | None
    target_type: str
    target_id: int
    params: dict
    changes: list[AuditChange]
    reason: str

    @staticmethod
    def resolve_championship_name(entry: AuditEntry) -> str | None:
        if entry.championship:
            return entry.championship.name
        return entry.championship_name or None


@router.get("/audit", response=list[AuditEntryOut])
def list_audit(request, championship_id: int | None = None, limit: int = 200):
    """League admins see every entry. A championship admin sees the entries of that championship."""
    entries = AuditEntry.objects.select_related("championship")
    if not is_league_admin(request.user):
        managed = ChampionshipMember.objects.filter(
            user=request.user, role=ChampionshipMember.Role.ADMIN
        ).values("championship_id")
        require(managed.exists())
        entries = entries.filter(championship_id__in=managed)
    if championship_id is not None:
        entries = entries.filter(championship_id=championship_id)
    return entries[: max(1, min(limit, 500))]
