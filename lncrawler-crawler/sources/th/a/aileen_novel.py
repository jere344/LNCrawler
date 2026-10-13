# -*- coding: utf-8 -*-
"""AileenNovel - disabled source.

Disabled: Cloudflare 403; search reports the site as offline.
"""

from lncrawl.core.crawler import Crawler


class AileenNovelCrawler(Crawler):
    base_url = "https://aileen-novel.online/"
    language = "th"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Cloudflare 403; search reports the site as offline'
