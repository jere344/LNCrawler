# -*- coding: utf-8 -*-
"""Novels108 (novels108.com). Disabled: bot wall, see disable_reason."""

from lncrawl.core.crawler import Crawler


class Novels108Crawler(Crawler):
    base_url = "https://novels108.com/"
    language = "th"

    is_disabled = True
    disable_reason = (
        "bot wall: Cloudflare challenge; curl 403; headless chromium still challenged at 25s"
    )
