# -*- coding: utf-8 -*-
"""BookGoodies (bookgoodies.com) - book deals blog, not a content host. Disabled: Book deals/freebies blog, not a content host."""

from lncrawl.core.crawler import Crawler


class BookGoodiesCrawler(Crawler):
    base_url = [
        "https://bookgoodies.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Book deals/freebies blog, not a content host"
    )
