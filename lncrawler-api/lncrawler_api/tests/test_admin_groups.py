from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase


class AdminGroupingTests(TestCase):
    def test_models_are_grouped_into_categories(self):
        user = get_user_model()(is_staff=True, is_superuser=True)
        user._state.adding = False
        request = RequestFactory().get("/admin/")
        request.user = user

        labels = [app["app_label"] for app in admin.site.get_app_list(request)]
        self.assertIn("novels", labels)
        self.assertIn("community", labels)
        self.assertNotIn("lncrawler_api", labels)
