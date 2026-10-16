# -*- coding: utf-8 -*-
"""shuhaige.net - Chinese web novel library.

Disabled: the host does not respond.
"""

from lncrawl.core.crawler import Crawler


class ShuhaigeCrawler(Crawler):
    base_url = "https://www.shuhaige.net"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Unreachable (no response from host)."
