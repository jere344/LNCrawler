# -*- coding: utf-8 -*-
"""Kitenovel (kitenovel.com). Disabled: copy of WebNovel text; novel and chapter lists come from a token-gated API."""

from lncrawl.core.crawler import Crawler


class KitenovelCrawler(Crawler):
    base_url = [
        "https://kitenovel.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Mirror of WebNovel: chapter bodies carry WebNovel markers, a copyright line and [New Text Published] headings, already covered by webnovel.py, and the novel and chapter list API returns 401 without the frontend-embedded token."
    )
