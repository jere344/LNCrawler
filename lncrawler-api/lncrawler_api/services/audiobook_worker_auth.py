"""Accounts of the audiobook workers: a Django user in WORKER_GROUP, authenticated with a DRF token.

The admin creates them with the ``create_audiobook_worker`` command. A worker user never logs in
with a password: its password is unusable and its token is the only credential.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.authtoken.models import Token
from rest_framework.permissions import BasePermission

WORKER_GROUP = 'audiobook_workers'
WORKER_EMAIL_DOMAIN = 'audiobook-worker.invalid'  # the user model needs a unique email; this one never receives mail


class IsAudiobookWorker(BasePermission):
    """Allows only authenticated users of the worker group."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.groups.filter(name=WORKER_GROUP).exists())


def ensure_worker_token(username, rotate=False):
    """Create the worker user and its group if missing, and return (token key, created_token).

    The token is only rotated when ``rotate`` is true; otherwise the existing one is returned.
    """
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=username,
        defaults={'email': f'{username}@{WORKER_EMAIL_DOMAIN}'},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    group, _ = Group.objects.get_or_create(name=WORKER_GROUP)
    user.groups.add(group)
    if rotate:
        Token.objects.filter(user=user).delete()
    token, created_token = Token.objects.get_or_create(user=user)
    return token.key, created_token
