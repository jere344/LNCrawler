# -*- coding: utf-8 -*-
"""mtlarabic.com — Arabic machine-translated (MTL) novels.

Intentionally not implemented: machine-translated content is extremely low
quality, so this source is kept only as a disabled stub.
"""

from lncrawl.core.crawler import Crawler


class MTLArabicCrawler(Crawler):
    base_url = "https://mtlarabic.com/"
    language = "ar"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
