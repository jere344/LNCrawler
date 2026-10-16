# -*- coding: utf-8 -*-
"""Storylog (storyloggroup.com, formerly storylog.co). Disabled."""
from lncrawl.core.crawler import Crawler


class StorylogCrawler(Crawler):
    base_url = ["https://storylog.co/", "https://www.storyloggroup.com/"]
    language = "th"
    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge on every request; curl 403, and a real browser "
        "is also stuck on 'Just a moment...' after ~8s (not resolved passively). "
        "Also blocked in a real browser"
    )
