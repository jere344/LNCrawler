# -*- coding: utf-8 -*-
"""VolareNovels (volarenovels.com). Disabled: React SPA with no discoverable public API."""

from lncrawl.core.crawler import Crawler


class VolareNovelsCrawler(Crawler):
    base_url = [
        "https://volarenovels.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "React SPA with no discoverable public API; needs a browser"
    )
