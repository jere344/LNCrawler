# -*- coding: utf-8 -*-
"""TruyenVn - disabled source.

Disabled: Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host.
"""

from lncrawl.core.crawler import Crawler


class TruyenVnCrawler(Crawler):
    base_url = "https://truyen.vn/"
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable (HTTP 000/522/530) or Cloudflare-blocked from the research host'
