from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from ..models.users_models import ReaderSettingsSlot
from ..serializers.users_serializers import READER_SETTINGS_MAX_BYTES


class ReaderSettingsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="reader", email="reader@example.com", password="x")
        self.other = get_user_model().objects.create_user(username="other", email="other@example.com", password="x")
        self.client.force_authenticate(self.user)

    def slot_url(self, slot="desktop"):
        return reverse("reader_settings_slot", kwargs={"slot": slot})

    def put(self, data, base_revision, slot="desktop", schema_version=1):
        return self.client.put(
            self.slot_url(slot),
            {"data": data, "schema_version": schema_version, "base_revision": base_revision},
            format="json",
        )

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get(self.slot_url()).status_code, 401)
        self.assertEqual(anonymous.get(reverse("list_reader_settings")).status_code, 401)

    def test_missing_copy_is_404(self):
        self.assertEqual(self.client.get(self.slot_url()).status_code, 404)

    def test_first_save_creates_revision_1(self):
        response = self.put({"fontSize": 20}, None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revision"], 1)

        response = self.client.get(self.slot_url())
        self.assertEqual(response.data["data"], {"fontSize": 20})
        self.assertEqual(response.data["revision"], 1)

    def test_save_from_current_revision_increments(self):
        self.put({"fontSize": 20}, None)
        response = self.put({"fontSize": 22}, 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(response.data["data"], {"fontSize": 22})

    def test_stale_revision_is_refused_with_current_copy(self):
        self.put({"fontSize": 20}, None)
        self.put({"fontSize": 22}, 1)

        response = self.put({"fontSize": 30}, 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(response.data["data"], {"fontSize": 22})
        self.assertEqual(ReaderSettingsSlot.objects.get(user=self.user).data, {"fontSize": 22})

    def test_first_save_cannot_overwrite_an_existing_copy(self):
        # A device that never saw the server copy sends null: it must not replace it
        self.put({"fontSize": 20}, None)
        response = self.put({"fontSize": 16}, None)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["data"], {"fontSize": 20})

    def test_revision_without_copy_is_refused(self):
        response = self.put({"fontSize": 20}, 3)
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(response.data["revision"])
        self.assertFalse(ReaderSettingsSlot.objects.exists())

    def test_device_types_are_separate(self):
        self.put({"fontSize": 20}, None, slot="desktop")
        self.put({"fontSize": 16}, None, slot="mobile")

        self.assertEqual(self.client.get(self.slot_url("desktop")).data["data"], {"fontSize": 20})
        self.assertEqual(self.client.get(self.slot_url("mobile")).data["data"], {"fontSize": 16})
        listing = self.client.get(reverse("list_reader_settings")).data
        self.assertEqual([row["slot"] for row in listing], ["desktop", "mobile"])
        self.assertNotIn("data", listing[0])

    def test_unknown_device_type_is_404(self):
        self.assertEqual(self.client.get(self.slot_url("tablet")).status_code, 404)
        self.assertEqual(self.put({}, None, slot="tablet").status_code, 404)

    def test_invalid_payloads_are_refused(self):
        self.assertEqual(self.put(["not", "an", "object"], None).status_code, 400)
        self.assertEqual(self.put({"fontSize": 20}, None, schema_version=0).status_code, 400)
        too_large = {"text": "x" * READER_SETTINGS_MAX_BYTES}
        self.assertEqual(self.put(too_large, None).status_code, 400)
        self.assertFalse(ReaderSettingsSlot.objects.exists())

    def test_users_only_see_their_own_settings(self):
        ReaderSettingsSlot.objects.create(user=self.other, slot="desktop", data={"fontSize": 40})

        self.assertEqual(self.client.get(self.slot_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("list_reader_settings")).data, [])
        self.assertEqual(self.put({"fontSize": 20}, None).status_code, 200)
        self.assertEqual(ReaderSettingsSlot.objects.get(user=self.other).data, {"fontSize": 40})
