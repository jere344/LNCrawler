# -*- coding: utf-8 -*-
"""HotTruyen - disabled source.

Disabled: Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host.
"""

from lncrawl.core.crawler import Crawler


class HotTruyenCrawler(Crawler):
    base_url = "https://hottruyen.vn/"
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host'
