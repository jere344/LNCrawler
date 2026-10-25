# -*- coding: utf-8 -*-
"""Readwn (readwn.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class ReadwnCrawler(Crawler):
    base_url = [
        "https://readwn.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Now serves Wuxia Box (same catalog as wuxiabox.py): machine-translated (MTL) content, intentionally excluded"
    )
