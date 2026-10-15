# -*- coding: utf-8 -*-
"""Kawebook (กวีบุ๊ค) — Thai licensed-translation novel store. Disabled."""
from lncrawl.core.crawler import Crawler


class KawebookCrawler(Crawler):
    base_url = ["https://www.kawebook.com/"]
    language = "th"
    is_disabled = True
    disable_reason = (
        "chapter text is glyph-remapped via custom web fonts (cs_prajad1/cs_prajad2), "
        "so raw HTML characters are not the real Thai text; paid chapters gated by "
        "coin/heart payment modals. Tested with curl (server-rendered, no bot wall)"
    )
