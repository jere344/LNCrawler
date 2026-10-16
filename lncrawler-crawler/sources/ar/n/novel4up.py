# -*- coding: utf-8 -*-
"""novel4up.com — former Arabic novel site.

The domain now serves gambling/affiliate spam (``/01-game/``, ``/24k-bet/``);
the original site is gone. Disabled.
"""

from lncrawl.core.crawler import Crawler


class Novel4UpCrawler(Crawler):
    base_url = "https://novel4up.com/"
    language = "ar"
    has_mtl = False

    is_disabled = True
    disable_reason = "Domain now serves gambling/affiliate spam; original site gone"
