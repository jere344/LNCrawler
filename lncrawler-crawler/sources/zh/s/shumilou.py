# -*- coding: utf-8 -*-
"""shumilou.net - Chinese web novel library.

Disabled: the site serves a degraded, ad-only page with a stub title instead
of a usable catalog or chapter content.
"""

from lncrawl.core.crawler import Crawler


class ShumilouCrawler(Crawler):
    base_url = "https://www.shumilou.net"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Site serves a degraded/ad-only page; no usable catalog or chapter content."
