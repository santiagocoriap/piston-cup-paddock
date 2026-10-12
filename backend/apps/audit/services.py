from typing import Any

from .models import AuditEntry

# Field names that must never reach the audit log.
FORBIDDEN_KEYS = {"password", "password_hash", "token", "secret", "credential", "credentials"}


def _check(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"The audit log must not store the field {key!r}.")
            _check(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _check(item)


def change(field: str, old: Any, new: Any) -> dict:
    return {"field": field, "old": old, "new": new}


def record(
    actor,
    action: str,
    target_type: str,
    target_id: int,
    *,
    championship=None,
    params: dict | None = None,
    changes: list[dict] | None = None,
    reason: str = "",
) -> AuditEntry:
    """Store one audit entry. Call it in the same transaction as the change."""
    params = params or {}
    changes = changes or []
    _check(params)
    _check(changes)
    return AuditEntry.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=getattr(actor, "username", "") or "system",
        action=action,
        championship=championship,
        target_type=target_type,
        target_id=target_id,
        params=params,
        changes=changes,
        reason=reason,
    )
