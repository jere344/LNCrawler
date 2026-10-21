"""The frontend error sink must drop extension/injected noise and stale-chunk
failures; these patterns are the production regression set."""

from django.test import SimpleTestCase

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
