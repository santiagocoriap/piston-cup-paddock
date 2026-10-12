"""Who can see and change a championship. Every check goes through this module."""

from django.db.models import QuerySet

from .models import Championship, ChampionshipMember


def is_league_admin(user) -> bool:
    return user.is_authenticated and user.is_staff


def visible_championships(user) -> QuerySet[Championship]:
    if is_league_admin(user):
        return Championship.objects.all()
    return Championship.objects.filter(members__user=user).distinct()


def can_view(user, championship: Championship) -> bool:
    return visible_championships(user).filter(pk=championship.pk).exists()


def can_manage(user, championship: Championship) -> bool:
    if is_league_admin(user):
        return True
    return ChampionshipMember.objects.filter(
        championship=championship, user=user, role=ChampionshipMember.Role.ADMIN
    ).exists()


def manages_any_championship(user) -> bool:
    if is_league_admin(user):
        return True
    return ChampionshipMember.objects.filter(user=user, role=ChampionshipMember.Role.ADMIN).exists()
