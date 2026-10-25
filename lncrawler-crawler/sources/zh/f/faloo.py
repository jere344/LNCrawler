# -*- coding: utf-8 -*-
"""Faloo (飞卢小说网, faloo.com). Disabled: most chapters are paid VIP, see disable_reason."""

from lncrawl.core.crawler import Crawler


class FalooCrawler(Crawler):
    base_url = ["https://b.faloo.com/", "https://www.faloo.com/"]
    language = "zh"

    is_disabled = True
    disable_reason = (
        "paid VIP chapters: only the first chapters are free, later ones return a login and VIP upgrade prompt; "
        "tested with curl_cffi scraper on home, novel 969757 (chapter 1 free, chapter 273 login/VIP prompt)"
    )
