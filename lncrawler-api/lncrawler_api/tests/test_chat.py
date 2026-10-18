"""Tests for the chat API."""

import json

from django.contrib.auth import get_user_model

from django.test import TestCase

from django.urls import reverse

from ..models import ChatMessage


class ChatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chatter", password="pw")
        self.list_url = reverse("list_chat")
        self.add_url = reverse("add_chat_message")

    def _post(self, payload, authenticated=False):
        if authenticated:
            self.client.force_login(self.user)
        return self.client.post(
            self.add_url, data=json.dumps(payload), content_type="application/json"
        )

    def test_anonymous_requires_author_name(self):
        response = self._post({"message": "hello"})
        self.assertEqual(response.status_code, 400)

    def test_anonymous_can_post_with_name(self):
        response = self._post({"message": "hello", "author_name": "anon"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "anon")
        self.assertIsNone(response.json()["user"])

    def test_anonymous_cannot_impersonate_registered_username(self):
        for name in ("chatter", "Chatter"):
            response = self._post({"message": "hello", "author_name": name})
            self.assertEqual(response.status_code, 400)

    def test_authenticated_author_name_autofilled(self):
        response = self._post({"message": "hello"}, authenticated=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "chatter")
        self.assertIsNotNone(response.json()["user"])

    def test_authenticated_author_name_cannot_be_spoofed(self):
        response = self._post(
            {"message": "hello", "author_name": "someoneelse"}, authenticated=True
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "chatter")

    def test_list_is_newest_first_and_paginated(self):
        for i in range(3):
            ChatMessage.objects.create(author_name="a", message=f"m{i}")
        response = self.client.get(self.list_url, {"page_size": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual([m["message"] for m in body["results"]], ["m2", "m1"])

    def test_reply_carries_parent_preview(self):
        parent = self._post({"message": "parent", "author_name": "a"}).json()
        response = self._post(
            {"message": "child", "author_name": "b", "parent_id": parent["id"]}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent"]["id"], parent["id"])
        self.assertEqual(response.json()["parent"]["message"], "parent")

    def test_reply_to_unknown_parent_is_400(self):
        import uuid

        response = self._post(
            {"message": "child", "author_name": "b", "parent_id": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 400)

    def test_message_too_long_is_400(self):
        response = self._post({"message": "x" * 10001, "author_name": "a"})
        self.assertEqual(response.status_code, 400)

    def test_contains_spoiler_round_trip(self):
        response = self._post(
            {"message": "spoiled", "author_name": "a", "contains_spoiler": True}
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["contains_spoiler"])


class ChatEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chatter", password="pw")
        self.other = get_user_model().objects.create_user(
            username="other", password="pw", email="other@example.com"
        )
        self.message = ChatMessage.objects.create(user=self.user, message="original")
        self.anon_message = ChatMessage.objects.create(author_name="anon", message="anon text")

    def _put(self, message_id, payload):
        url = reverse("edit_chat_message", args=[message_id])
        return self.client.put(url, data=json.dumps(payload), content_type="application/json")

    def test_anonymous_cannot_edit_is_401(self):
        response = self._put(self.message.id, {"message": "changed"})
        self.assertEqual(response.status_code, 401)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, "original")

    def test_other_user_cannot_edit_is_403(self):
        self.client.force_login(self.other)
        response = self._put(self.message.id, {"message": "changed"})
        self.assertEqual(response.status_code, 403)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, "original")

    def test_cannot_edit_anonymous_message_is_403(self):
        self.client.force_login(self.user)
        response = self._put(self.anon_message.id, {"message": "changed"})
        self.assertEqual(response.status_code, 403)
        self.anon_message.refresh_from_db()
        self.assertEqual(self.anon_message.message, "anon text")

    def test_owner_can_edit(self):
        self.client.force_login(self.user)
        response = self._put(self.message.id, {"message": "  changed  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "changed")
        self.assertTrue(response.json()["edited"])
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, "changed")
        self.assertTrue(self.message.edited)

    def test_blank_message_is_400(self):
        self.client.force_login(self.user)
        response = self._put(self.message.id, {"message": "   "})
        self.assertEqual(response.status_code, 400)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, "original")
        self.assertFalse(self.message.edited)

    def test_message_too_long_is_400(self):
        self.client.force_login(self.user)
        response = self._put(self.message.id, {"message": "x" * 10001})
        self.assertEqual(response.status_code, 400)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, "original")

    def test_unknown_message_is_404(self):
        import uuid

        self.client.force_login(self.user)
        response = self._put(uuid.uuid4(), {"message": "changed"})
        self.assertEqual(response.status_code, 404)
