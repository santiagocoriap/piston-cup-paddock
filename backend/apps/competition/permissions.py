"""Who can see and change a championship. Every check goes through this module."""

from django.db.models import QuerySet

from .models import Championship, ChampionshipMember

# What a member can change in a championship. An admin can do all of them.
CAPABILITIES = ["results", "penalties", "restarts", "reports", "records"]
STEWARD_CAPABILITIES = {"penalties", "restarts"}


def is_league_admin(user) -> bool:
    return user.is_authenticated and user.is_staff


def visible_championships(user) -> QuerySet[Championship]:
    if is_league_admin(user):
        return Championship.objects.all()
    return Championship.objects.filter(members__user=user).distinct()


def can_view(user, championship: Championship) -> bool:
    return visible_championships(user).filter(pk=championship.pk).exists()


def can_manage(user, championship: Championship) -> bool:
    """Full control of the championship: seasons, entries, members, and all capabilities."""
    if is_league_admin(user):
        return True
    return ChampionshipMember.objects.filter(
        championship=championship, user=user, role=ChampionshipMember.Role.ADMIN
    ).exists()


def capabilities(user, championship: Championship) -> set[str]:
    if not user.is_authenticated:
        return set()
    if is_league_admin(user):
        return set(CAPABILITIES)
    member = (
        ChampionshipMember.objects.filter(championship=championship, user=user)
        .select_related("custom_role")
        .first()
    )
    if member is None:
        return set()
    if member.role == ChampionshipMember.Role.ADMIN:
        return set(CAPABILITIES)
    if member.role == ChampionshipMember.Role.STEWARD:
        return set(STEWARD_CAPABILITIES)
    if member.role == ChampionshipMember.Role.CUSTOM and member.custom_role:
        # The role check stops a role of another championship.
        if member.custom_role.championship_id == championship.id:
            return set(member.custom_role.capabilities) & set(CAPABILITIES)
    return set()


def can(user, championship: Championship, capability: str) -> bool:
    return capability in capabilities(user, championship)


def manages_any_championship(user) -> bool:
    if is_league_admin(user):
        return True
    return ChampionshipMember.objects.filter(user=user, role=ChampionshipMember.Role.ADMIN).exists()


def has_any_staff_role(user) -> bool:
    """True when the admin mode is useful: an admin, a steward, or a custom role."""
    if manages_any_championship(user):
        return True
    return ChampionshipMember.objects.filter(
        user=user,
        role__in=[ChampionshipMember.Role.STEWARD, ChampionshipMember.Role.CUSTOM],
    ).exists()
