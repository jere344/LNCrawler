# -*- coding: utf-8 -*-
"""ranobelib.me — Russian translation library (SPA).

The site is a single-page app (``/build/assets/main-*.js``). Its API at
``api.cdnlibs.org/api/manga/*`` returns 403 to plain clients even with
``Site-Id: 3``, and a browser-level session is required, which the pipeline
does not have. Disabled.
"""

from lncrawl.core.crawler import Crawler


class RanobeLibCrawler(Crawler):
    base_url = "https://ranobelib.me/"
    language = "ru"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "SPA; API returns 403 to non-browser clients and needs a browser session"
    )
