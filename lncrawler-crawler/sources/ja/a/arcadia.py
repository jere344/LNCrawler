# -*- coding: utf-8 -*-
"""Arcadia (arcadia.jp). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class ArcadiaCrawler(Crawler):
    base_url = "https://arcadia.jp/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the test environment (curl timed out after 40 s, 3 attempts each); not evaluated. Retry from another network before revisiting.'
