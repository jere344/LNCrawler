"""The crawler's default Origin/Referer header values must stay Latin-1 safe."""

from django.test import SimpleTestCase

from ..utils.crawler_path import ensure_crawler_on_path

ensure_crawler_on_path()
from lncrawl.core.scraper import _header_url  # noqa: E402


class HeaderUrlTests(SimpleTestCase):
    def test_ascii_url_is_unchanged(self):
        url = "https://example.com/novel/a%20b?x=1&y=%C3%A9#top"
        self.assertEqual(_header_url(url), url)

    def test_non_ascii_path_is_percent_encoded(self):
        self.assertEqual(
            _header_url("https://example.com/novel/é"),
            "https://example.com/novel/%C3%A9",
        )

    def test_existing_percent_escapes_are_kept(self):
        self.assertEqual(
            _header_url("https://example.com/é%20x"),
            "https://example.com/%C3%A9%20x",
        )

    def test_idn_host_becomes_punycode(self):
        self.assertEqual(
            _header_url("https://bücher.de/x"),
            "https://xn--bcher-kva.de/x",
        )

    def test_port_is_preserved_with_idn_host(self):
        self.assertEqual(
            _header_url("https://bücher.de:8443/x"),
            "https://xn--bcher-kva.de:8443/x",
        )
