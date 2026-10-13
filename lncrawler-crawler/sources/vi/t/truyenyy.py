# -*- coding: utf-8 -*-
"""TruyenYy - disabled source.

Disabled: Cloudflare 'Attention Required' 403 on the root.
"""

from lncrawl.core.crawler import Crawler


class TruyenYyCrawler(Crawler):
    base_url = "https://truyenyy.mobi/"
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = "Cloudflare 'Attention Required' 403 on the root"
