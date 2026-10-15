# -*- coding: utf-8 -*-
"""shumilou.net - Chinese web novel library.

Disabled: the domain is parked and listed for sale. Every path returns the
same 4 KB domain-sale page, even with browser impersonation.
"""

from lncrawl.core.crawler import Crawler


class ShumilouCrawler(Crawler):
    base_url = "https://www.shumilou.net"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "(Domain parked and for sale: every path, incl. search/book/chapter/sitemap, returns the same 4 KB domain-sale page. Tested with curl_cffi browser impersonation (chrome) on 2026-10-14; no catalog or chapter content exists.)"
