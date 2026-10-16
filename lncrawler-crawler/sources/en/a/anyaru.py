# -*- coding: utf-8 -*-
"""Anyaru (anyaru.com). Disabled: Content could not be verified (homepage returns 200, /novels returns 404)."""

from lncrawl.core.crawler import Crawler


class AnyaruCrawler(Crawler):
    base_url = [
        "https://anyaru.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Content could not be verified (homepage returns 200, /novels returns 404)"
    )
