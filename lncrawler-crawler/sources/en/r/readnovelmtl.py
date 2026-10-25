# -*- coding: utf-8 -*-
"""ReadNovelMTL (readnovelmtl.com) - machine-translated novels. Cloudflare returns 403 to curl and curl_cffi. Disabled: Machine-translated (MTL) content — extremely low quality, intentionally excluded."""

from lncrawl.core.crawler import Crawler


class ReadNovelMTLCrawler(Crawler):
    base_url = [
        "https://readnovelmtl.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
