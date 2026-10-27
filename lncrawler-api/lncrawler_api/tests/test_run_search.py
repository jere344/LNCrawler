"""Tests for the cross-source search loop in lncrawl.core.search."""

import time
from unittest import mock

from django.test import SimpleTestCase


def _fast_source(title, url):
    class FastSource:
        source_name = url

        def __init__(self):
            self.request_timeout = None

        def initialize(self):
            pass

        def search_novel(self, query):
            return [{"title": title, "url": url, "info": None}]

        def close(self):
            pass

    return FastSource


def _delayed_source(seconds, title, url):
    class DelayedSource(_fast_source(title, url)):
        def search_novel(self, query):
            time.sleep(seconds)
            return [{"title": title, "url": url, "info": None}]

    return DelayedSource


def _slow_source(seconds):
    class SlowSource(_fast_source("Slow Novel", "http://slow/1")):
        def search_novel(self, query):
            time.sleep(seconds)
            return [{"title": "Slow Novel", "url": "http://slow/1", "info": None}]

    return SlowSource


class RunSearchTests(SimpleTestCase):
    def setUp(self):
        from lncrawler_api.services.downloader_service import _load_app

        _load_app()
        from lncrawl.core import search

        self.search = search

    def _run(self, crawlers, **kwargs):
        with mock.patch.object(
            self.search, "get_search_crawlers", return_value=crawlers
        ):
            return self.search.run_search("solo leveling", **kwargs)

    def test_on_results_receives_growing_ranked_lists(self):
        crawlers = [
            _delayed_source(0.2, "Solo Leveling", "http://a/1"),
            _delayed_source(0.8, "Solo Leveling", "http://b/1"),
            _delayed_source(1.4, "Other Story", "http://c/1"),
        ]
        snapshots = []

        result = self._run(crawlers, on_results=lambda ranked: snapshots.append(ranked))

        self.assertGreater(len(snapshots), 1)
        sizes = [sum(len(g["novels"]) for g in ranked) for ranked in snapshots]
        self.assertEqual(sizes, sorted(sizes))
        self.assertEqual(snapshots[-1], result)
        self.assertEqual(result[0]["title"], "Solo Leveling")
        self.assertEqual(len(result[0]["novels"]), 2)

    def test_grace_window_stops_waiting_for_a_straggler(self):
        crawlers = [_fast_source(f"Novel {i}", f"http://n/{i}") for i in range(19)]
        crawlers.append(_slow_source(5))

        with mock.patch.object(self.search, "SEARCH_TIMEOUT", 30), mock.patch.object(
            self.search, "STRAGGLER_GRACE", 0.5
        ):
            started = time.monotonic()
            result = self._run(crawlers)
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 3)
        titles = {group["title"] for group in result}
        self.assertEqual(len(titles), 19)
        self.assertNotIn("Slow Novel", titles)

    def test_should_stop_ends_the_search_early(self):
        crawlers = [_slow_source(5)]

        with mock.patch.object(self.search, "SEARCH_TIMEOUT", 30):
            started = time.monotonic()
            result = self._run(crawlers, should_stop=lambda: True)
            elapsed = time.monotonic() - started

        self.assertEqual(result, [])
        self.assertLess(elapsed, 2)

    def test_rank_results_builds_fresh_objects(self):
        raw = [{"title": "Solo Leveling", "url": "http://a/1", "info": None}]

        first = self.search.rank_results("solo", raw)
        second = self.search.rank_results("solo", raw)

        self.assertEqual(first, second)
        self.assertIsNot(first[0]["novels"], second[0]["novels"])
        self.assertIsNot(first[0]["novels"][0], second[0]["novels"][0])

    def test_results_per_source_are_capped(self):
        class FloodSource(_fast_source("unused", "http://flood")):
            def search_novel(self, query):
                return [
                    {"title": f"Novel {i}", "url": f"http://flood/{i}", "info": None}
                    for i in range(80)
                ]

        result = self._run([FloodSource])

        self.assertEqual(len(result), self.search.MAX_RESULTS_PER_SOURCE)
