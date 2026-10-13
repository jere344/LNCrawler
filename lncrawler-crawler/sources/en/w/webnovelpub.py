# -*- coding: utf-8 -*-
"""WebNovelPub (webnovelpub.com). Disabled: Bot-protected: redirects to a JS challenge page (?ch=1&js=...)."""

from lncrawl.core.crawler import Crawler


class WebnovelPubCrawler(Crawler):
    base_url = [
        "https://webnovelpub.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Bot-protected: redirects to a JS challenge page (?ch=1&js=...); not reachable with plain HTTP"
    )
