# -*- coding: utf-8 -*-
"""Novellive (novellive.app) — English web novel site.

Disabled: the crawler's scraper gets 403 on https://novellive.app/ with the
Cloudflare "Just a moment..." challenge page (cf-mitigated: challenge). Not
checked in a real browser.
"""

from lncrawl.core.crawler import Crawler


class NovelliveCrawler(Crawler):
    base_url = ["https://novellive.app/"]
    language = "en"
    is_disabled = True
    disable_reason = "Cloudflare challenge page (403) via scraper; not checked in a browser"
