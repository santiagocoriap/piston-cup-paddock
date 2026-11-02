"""Merge two driver profiles of the same person into one.

Every row that points to the old profile moves to the kept profile: season entries, laps,
career adjustments, restarts, and records. The old profile goes away. The audit trail keeps
the merge with both names.
"""

from django.db import transaction

from apps.audit.services import change, record

from .models import DriverProfile, DriverSteamId


class MergeError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _relations():
    for field in DriverProfile._meta.get_fields(include_hidden=True):
        if field.is_relation and field.auto_created and not field.concrete:
            yield field.related_model, field.field.name, field.one_to_one


def check(old: DriverProfile, kept: DriverProfile) -> None:
    if old.pk == kept.pk:
        raise MergeError("same_driver")
    if old.user_id and kept.user_id:
        raise MergeError("both_have_accounts")
    old_seasons = set(old.entries.values_list("season_id", flat=True))
    if old_seasons & set(kept.entries.values_list("season_id", flat=True)):
        raise MergeError("both_in_season")


def merge(old: DriverProfile, kept: DriverProfile, user, reason: str) -> DriverProfile:
    check(old, kept)
    moved: dict[str, int] = {}
    with transaction.atomic():
        for model, field, one_to_one in _relations():
            rows = model.objects.filter(**{field: old})
            if one_to_one:
                # The kept profile keeps its own key or settings. Without one, it takes the old.
                if model.objects.filter(**{field: kept}).exists():
                    rows.delete()
                    continue
            count = rows.update(**{field: kept})
            if count:
                moved[f"{model.__name__}.{field}"] = count
        old_name, old_user = old.display_name, old.user
        old_guid = old.steam_guid
        old.delete()
        if old_guid and not kept.steam_guid:
            kept.steam_guid = old_guid
        elif old_guid and old_guid != kept.steam_guid:
            DriverSteamId.objects.create(driver=kept, guid=old_guid)
        if old_user and not kept.user_id:
            kept.user = old_user
        kept.save()
        record(
            user,
            "driver.merged",
            "driver",
            kept.id,
            params={"old": old_name, "kept": kept.display_name},
            changes=[change(name, None, count) for name, count in sorted(moved.items())],
            reason=reason,
        )
    return kept
