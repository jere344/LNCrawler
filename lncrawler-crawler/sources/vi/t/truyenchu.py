# -*- coding: utf-8 -*-
"""TruyenChuVn - disabled source.

Disabled: Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host.
"""

from lncrawl.core.crawler import Crawler


class TruyenChuVnCrawler(Crawler):
    base_url = "https://truyenchu.vn/"
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host'
