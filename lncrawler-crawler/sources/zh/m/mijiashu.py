# -*- coding: utf-8 -*-
"""mijiashu.com - Chinese web novel library.

Disabled: the host does not respond.
"""

from lncrawl.core.crawler import Crawler


class MijiashuCrawler(Crawler):
    base_url = "https://www.mijiashu.com"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Unreachable (no response from host)."
