"""The connections of an account: the MCP clients (for example Claude) that the person allowed.
The person sees them and can remove each one."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone
from ninja import Router, Schema, Status
from oauth2_provider.models import get_access_token_model, get_refresh_token_model

from apps.audit.services import record

router = Router(tags=["connections"])


class ConnectionOut(Schema):
    application_id: int
    name: str
    connected_at: datetime  # The first access of this client to the account.
    last_access_at: datetime  # The newest access token.
    active: bool  # A token that still works.


@router.get("/me/connections", response=list[ConnectionOut])
def connections(request):
    now = timezone.now()
    rows: dict[int, ConnectionOut] = {}
    tokens = get_access_token_model().objects.filter(user=request.user, application__isnull=False)
    for token in tokens.select_related("application").order_by("created"):
        app = token.application
        row = rows.get(app.id)
        if row is None:
            row = rows[app.id] = ConnectionOut(
                application_id=app.id,
                name=app.name,
                connected_at=token.created,
                last_access_at=token.created,
                active=False,
            )
        row.last_access_at = token.created
        row.active = row.active or token.expires > now
    refresh = get_refresh_token_model().objects.filter(
        user=request.user, revoked__isnull=True, application_id__in=rows
    )
    for token in refresh:
        rows[token.application_id].active = True
    return sorted(rows.values(), key=lambda r: r.last_access_at, reverse=True)


@router.delete("/me/connections/{application_id}", response={204: None})
def remove_connection(request, application_id: int):
    """Remove the access of one client to this account. The client must sign in again."""
    access = get_access_token_model().objects.filter(
        user=request.user, application_id=application_id
    )
    refresh = get_refresh_token_model().objects.filter(
        user=request.user, application_id=application_id
    )
    name = next((t.application.name for t in access.select_related("application")[:1]), "")
    with transaction.atomic():
        refresh.delete()
        access.delete()
        record(
            request.user,
            "account.connection_removed",
            "account",
            request.user.id,
            params={"username": request.user.username, "client": name},
        )
    return Status(204, None)
