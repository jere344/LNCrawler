# -*- coding: utf-8 -*-
"""Hetushu (hetushu.com). Disabled: bot wall, see disable_reason."""

from lncrawl.core.crawler import Crawler


class HetushuCrawler(Crawler):
    base_url = "https://www.hetushu.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "bot wall: Cloudflare managed challenge; curl 403; headless chromium still on 'Just a moment' at 25s"
    )
