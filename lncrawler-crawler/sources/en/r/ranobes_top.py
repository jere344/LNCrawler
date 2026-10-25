# -*- coding: utf-8 -*-
"""Ranobes Top (ranobes.top). Disabled: Cloudflare security check on every page, still unresolved in a real browser."""
from lncrawl.core.crawler import Crawler


class RanobesTopCrawler(Crawler):
    base_url = ["https://ranobes.top/", "https://ranobes.net/"]
    language = "en"
    is_disabled = True
    disable_reason = "Cloudflare security check on every page, still unresolved in a real browser after an 8 second wait; not solved"
