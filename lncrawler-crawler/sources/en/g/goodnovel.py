# -*- coding: utf-8 -*-
"""GoodNovel (goodnovel.com). Disabled: Coin/paid unlock model."""

from lncrawl.core.crawler import Crawler


class GoodNovelCrawler(Crawler):
    base_url = [
        "https://goodnovel.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Coin/paid unlock model; chapters are paywalled"
    )
