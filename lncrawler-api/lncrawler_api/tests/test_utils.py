"""Tests for shared helper utilities."""

from django.contrib.auth import get_user_model

from django.test import TestCase


class DedupHelperTests(TestCase):
    """Guards the shared helpers extracted from duplicated view/serializer code."""

    def test_friend_user_queryset_returns_accepted_either_direction(self):
        from ..models.users_models import Friendship
        from ..views.friends_views import friend_user_queryset

        User = get_user_model()
        alice = User.objects.create_user(username="alice", email="alice@x.com", password="x")
        bob = User.objects.create_user(username="bob", email="bob@x.com", password="x")
        carol = User.objects.create_user(username="carol", email="carol@x.com", password="x")
        Friendship.objects.create(requester=alice, addressee=bob, status=Friendship.ACCEPTED)
        Friendship.objects.create(requester=carol, addressee=alice, status=Friendship.PENDING)

        self.assertEqual(set(friend_user_queryset(alice)), {bob})
        self.assertEqual(set(friend_user_queryset(bob)), {alice})

    def test_build_media_url_encodes_and_prefixes(self):
        from ..utils import build_media_url

        self.assertIsNone(build_media_url(None))
        self.assertTrue(build_media_url("a b/cover.jpg").endswith("/a%20b/cover.jpg"))
