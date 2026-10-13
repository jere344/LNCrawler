# -*- coding: utf-8 -*-
"""LNMTL (lnmtl.com) - machine-translated light novels. Disabled: Machine-translated (MTL) content — extremely low quality, intentionally excluded."""

from lncrawl.core.crawler import Crawler


class LNMTLCrawler(Crawler):
    base_url = [
        "https://lnmtl.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
