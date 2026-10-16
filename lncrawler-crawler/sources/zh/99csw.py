# -*- coding: utf-8 -*-
"""99csw (99csw.com). Disabled: bot wall, see disable_reason."""

from lncrawl.core.crawler import Crawler


class CswCrawler(Crawler):
    base_url = "https://www.99csw.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "bot wall: Cloudflare challenge; curl 403; headless chromium still challenged at 25s"
    )
