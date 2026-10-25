# -*- coding: utf-8 -*-
"""33bqg (笔趣阁, 33bqg.com; 3bqg.cc redirects here). Disabled: human-verify gate, see disable_reason."""

from lncrawl.core.crawler import Crawler


class Bqg33Crawler(Crawler):
    base_url = ["https://www.33bqg.com/", "https://m.33bqg.com/"]
    language = "zh"

    is_disabled = True
    disable_reason = (
        "chapter pages are a JS shell ('加载中') that redirects to /user/verify.html, a human-verify gate; "
        "tested with curl_cffi scraper on home, /book/10376/ and chapter 1 and 2 (desktop and m. hosts)"
    )
