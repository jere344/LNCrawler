# -*- coding: utf-8 -*-
"""NovelMTL (novelmtl.app / novelmtl.com) - machine-translated novels. Disabled: Machine-translated (MTL) content — extremely low quality, intentionally excluded."""

from lncrawl.core.crawler import Crawler


class NovelMTLCrawler(Crawler):
    base_url = [
        "https://novelmtl.app/",
        "https://novelmtl.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
