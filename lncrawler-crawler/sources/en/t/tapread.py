# -*- coding: utf-8 -*-
"""TapRead (tapread.com) - Nuxt app with a coin-paywall model. Disabled: Monetised coin model (paywalled chapters)."""

from lncrawl.core.crawler import Crawler


class TapReadCrawler(Crawler):
    base_url = [
        "https://tapread.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Monetised coin model (paywalled chapters); book-list route not verified"
    )
