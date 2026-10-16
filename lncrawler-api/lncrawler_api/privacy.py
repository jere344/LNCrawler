from django.db.models import Q

from .models.users_models import Friendship


def are_friends(a, b):
    """True when two authenticated users have an accepted friendship."""
    if not a or not b:
        return False
    if not getattr(a, 'is_authenticated', False) or not getattr(b, 'is_authenticated', False):
        return False
    if a.id == b.id:
        return False
    return Friendship.objects.filter(status=Friendship.ACCEPTED).filter(
        Q(requester=a, addressee=b) | Q(requester=b, addressee=a)
    ).exists()


def can_view(viewer, owner, section):
    """Whether `viewer` may see `section` of `owner`'s profile."""
    if viewer is not None and getattr(viewer, 'is_authenticated', False) and viewer.id == owner.id:
        return True
    visibility = owner.visibility(section)
    if visibility == 'public':
        return True
    if visibility == 'friends':
        return are_friends(viewer, owner)
    return False
