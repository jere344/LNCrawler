# -*- coding: utf-8 -*-
"""NovelTR (noveltr.com) - Turkish translated web-novel site.

The domain no longer hosts the novel site.  As of 2025 it was dropped and
re-registered as a German-language travel blog (WordPress, "noveltr.com -
Deine Inspiration fuer unvergessliche Reisen.").  The former novel URLs
(``/series/<slug>/``) now return 404 and no mirror resolves: ``noveltr.net``
(and every other TLD tried) has no DNS record.  Nothing to crawl; disabled
until a live mirror/relaunch appears.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovelTRCrawler(Crawler):
    base_url = [
        "https://noveltr.com/",
        "https://www.noveltr.com/",
    ]
    language = "tr"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Domain repurposed: noveltr.com is now a German travel blog; the former "
        "/series/ pages return 404 and no mirror (noveltr.net, etc.) resolves. "
        "Original Turkish novel site is offline."
    )
