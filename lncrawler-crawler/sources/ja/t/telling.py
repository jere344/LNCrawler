# -*- coding: utf-8 -*-
"""Telling (telling.asia). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class TellingCrawler(Crawler):
    base_url = "https://telling.asia/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the test environment (curl timed out after 40 s, 3 attempts each); not evaluated. Retry from another network before revisiting.'
