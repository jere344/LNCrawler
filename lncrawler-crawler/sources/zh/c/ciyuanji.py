# -*- coding: utf-8 -*-
"""Ciyuanji (次元姬, ciyuanji.com). Disabled: VIP chapters behind login and coin system, see disable_reason."""

from lncrawl.core.crawler import Crawler


class CiyuanjiCrawler(Crawler):
    base_url = "https://www.ciyuanji.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "VIP chapters require login and a coin (书币) top-up; some chapters redirect to /login, others are free "
        "so the lock cannot be detected reliably from the chapter list; tested with curl_cffi scraper on home "
        "and 5 chapter pages (2 free, 2 redirect to /login, 1 announcement)"
    )
