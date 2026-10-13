# -*- coding: utf-8 -*-
"""BookToki / NewToki (booktoki.net). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class BooktokiCrawler(Crawler):
    base_url = "https://booktoki.net/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Reachable, but the content is mostly reposted or pirated web novels rather than original content. Excluded on the original-content criterion (copyright and legal risk).'
