# -*- coding: utf-8 -*-
"""Dragonholic (dragonholic.com). Disabled: Site moved to a new domain."""

from lncrawl.core.crawler import Crawler


class DragonholicCrawler(Crawler):
    base_url = [
        "https://dragonholic.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Site moved to a new domain; the new link is not published (Discord invite only)"
    )
