# -*- coding: utf-8 -*-
"""KisahNovel - disabled source.

Disabled: Unreachable from the research host (DNS/connection failure, HTTP 000).
"""

from lncrawl.core.crawler import Crawler


class KisahNovelCrawler(Crawler):
    base_url = "https://kisahnovel.com/"
    language = "id"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the research host (DNS/connection failure, HTTP 000)'
