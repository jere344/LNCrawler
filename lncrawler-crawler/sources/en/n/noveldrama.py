# -*- coding: utf-8 -*-
"""NoveDrama (noveldrama.com). Disabled: Redirect loop to a JS challenge page."""

from lncrawl.core.crawler import Crawler


class NovelDramaCrawler(Crawler):
    base_url = [
        "https://noveldrama.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Redirect loop to a JS challenge page"
    )
