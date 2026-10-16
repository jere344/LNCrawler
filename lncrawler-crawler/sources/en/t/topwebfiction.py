# -*- coding: utf-8 -*-
"""TopWebFiction (topwebfiction.com) - directory of original fiction. Disabled: Directory of original English web fiction, not translations."""

from lncrawl.core.crawler import Crawler


class TopWebFictionCrawler(Crawler):
    base_url = [
        "https://topwebfiction.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Directory of original English web fiction, not translations"
    )
