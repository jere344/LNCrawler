# -*- coding: utf-8 -*-
"""Novelabo (novelabo.net). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class NovelaboCrawler(Crawler):
    base_url = "https://novelabo.net/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the test environment (curl timed out after 40 s, 3 attempts each); not evaluated. Retry from another network before revisiting.'
