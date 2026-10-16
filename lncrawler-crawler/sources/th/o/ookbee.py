# -*- coding: utf-8 -*-
"""Ookbee — Thai commercial e-book store. Disabled."""
from lncrawl.core.crawler import Crawler


class OokbeeCrawler(Crawler):
    base_url = ["https://www.ookbee.com/"]
    language = "th"
    is_disabled = True
    disable_reason = (
        "commercial e-book store: only trial excerpts ('ทดลองอ่าน') are free, full text "
        "requires purchase or the app. Tested with curl (Next.js SSR; /api/public/novel "
        "endpoints not usable)"
    )
