# -*- coding: utf-8 -*-
"""qidian.com / read.qidian.com - Yuewen flagship platform.

Disabled: requests return HTTP 202 with an empty ~209-byte body, a
bot-detection response. Most chapters are also paywalled.
"""

from lncrawl.core.crawler import Crawler


class QidianCrawler(Crawler):
    base_url = ["https://www.qidian.com/", "https://read.qidian.com/"]
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "HTTP 202 empty response (bot detection) on qidian.com and read.qidian.com; most chapters paywalled."
