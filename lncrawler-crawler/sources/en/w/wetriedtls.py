# -*- coding: utf-8 -*-
"""We Tried TLS (wetriedtls.com). Disabled: human translations, but only the first 21 of 41 chapters are free; the rest are premium."""

from lncrawl.core.crawler import Crawler


class WeTriedTlsCrawler(Crawler):
    base_url = [
        "https://wetriedtls.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Only the first 21 of 41 chapters are free; the rest are premium behind a coin cost, so a crawl would be a partial novel."
    )
