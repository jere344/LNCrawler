"""The frontend error sink must drop extension/injected noise and stale-chunk
failures; these patterns are the production regression set."""

import json

from django.test import SimpleTestCase
from django.urls import reverse

from lncrawler_api.views.errors_views import _IGNORABLE, _is_extension_error


class IgnorableMessageTests(SimpleTestCase):
    def test_extension_and_injected_messages_are_ignored(self):
        for message in (
            "Can't find variable: __firefox__",
            "undefined is not an object (evaluating 'window.__firefox__.reader')",
            "error loading dynamically imported module: https://lncrawler.monster/assets/SettingsPage-x.js",
            "Importing a module script failed.",
            "Failed to execute 'removeChild' on 'Node': The node to be removed is not a child of this node.",
            "Failed to execute 'insertBefore' on 'Node': The node before which the new node is to be inserted is not a child of this node.",
            "The object can not be found here.",
        ):
            self.assertIsNotNone(_IGNORABLE.search(message), message)

    def test_real_errors_are_not_ignored(self):
        for message in (
            "Request failed with status code 500",
            "Maximum call stack size exceeded.",
        ):
            self.assertIsNone(_IGNORABLE.search(message), message)


class InjectedFrameTests(SimpleTestCase):
    def test_document_frame_is_treated_as_injected(self):
        stack = "@https://lncrawler.monster/novels/x/novelhallcom/chapter/1:189:70\n@https://lncrawler.monster/assets/index-abc.js:9:1"
        self.assertTrue(_is_extension_error(stack))

    def test_our_asset_frame_is_not_injected(self):
        stack = "    at Po (https://lncrawler.monster/assets/api-abc.js:38:115)"
        self.assertFalse(_is_extension_error(stack))

    def test_extension_scheme_frame_is_detected(self):
        stack = "    at handler (moz-extension://abcd/script.js:1:1)"
        self.assertTrue(_is_extension_error(stack))


class BotUserAgentTests(SimpleTestCase):
    def _post(self, user_agent):
        return self.client.post(
            reverse("report_error"),
            json.dumps({"message": "boom"}),
            content_type="application/json",
            HTTP_USER_AGENT=user_agent,
        )

    def test_crawler_user_agents_are_ignored(self):
        for user_agent in (
            "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "bingbot/2.0",
        ):
            self.assertEqual(self._post(user_agent).json(), {"detail": "ignored"}, user_agent)

    def test_browser_user_agents_are_reported(self):
        for user_agent in (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; CUBOT P50) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 11; CUBOT; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/141.0.0.0 Mobile Safari/537.36",
            "Dalvik/2.1.0 (Linux; U; Android 10; CUBOT/X19 Build/QP1A.190711.020)",
        ):
            # assertLogs swaps out the GitHub-issue handler, so nothing is filed.
            with self.assertLogs("frontend", level="ERROR"):
                self.assertEqual(self._post(user_agent).json(), {"detail": "ok"}, user_agent)

    def test_render_seo_header_marks_a_bot_even_with_a_browser_user_agent(self):
        response = self.client.post(
            reverse("report_error"),
            json.dumps({"message": "boom"}),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            HTTP_X_RENDER_SEO="1",
        )
        self.assertEqual(response.json(), {"detail": "ignored"})
