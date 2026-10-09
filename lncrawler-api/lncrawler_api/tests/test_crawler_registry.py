"""Tests for crawler registry liveness checks."""

from django.test import TestCase


class HasCrawlerTests(TestCase):
    """Liveness helper behind the greyed-out Update button."""

    def setUp(self):
        from lncrawler_api.utils import crawler_registry

        self.registry = crawler_registry
        self.registry._cache.clear()
        # Resolve the crawler package path so ``patch`` can import lncrawl below.
        self.registry.has_crawler("https://warmup.invalid/__warm__")
        self.registry._cache.clear()

    def test_empty_and_non_http_are_dead(self):
        self.assertFalse(self.registry.has_crawler(""))
        self.assertFalse(self.registry.has_crawler("example.com/novel"))

    def test_live_missing_and_disabled_crawlers(self):
        from unittest.mock import patch

        live = type("Live", (), {"is_disabled": False, "disable_reason": None})
        disabled = type("Disabled", (), {"is_disabled": True, "disable_reason": None})
        dead = type("Reason", (), {"is_disabled": False, "disable_reason": "gone"})
        url = "https://example.com/x"

        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=live):
            self.assertTrue(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=disabled):
            self.assertFalse(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=dead):
            self.assertFalse(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=None):
            self.assertFalse(self.registry.has_crawler(url))

    def test_registry_failure_fails_open_and_is_not_cached(self):
        from unittest.mock import patch

        url = "https://example.com/x"
        with patch("lncrawl.core.sources.get_crawler_by_url", side_effect=RuntimeError):
            self.assertTrue(self.registry.has_crawler(url))
        live = type("Live", (), {"is_disabled": False, "disable_reason": None})
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=live):
            self.assertTrue(self.registry.has_crawler(url))
