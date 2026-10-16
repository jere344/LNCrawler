# -*- coding: utf-8 -*-
"""novelsnet.com — Wix marketing blog ("Blog | NovelsNet").

No novel content was verified on the site. Language is unknown; ``en`` is
used as a placeholder. Disabled.
"""

from lncrawl.core.crawler import Crawler


class NovelsNetCrawler(Crawler):
    base_url = "https://novelsnet.com/"
    language = "en"
    has_mtl = False

    is_disabled = True
    disable_reason = "Wix marketing blog; no novel content verified"
