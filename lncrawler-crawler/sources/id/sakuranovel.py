# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class SakuraNovelCrawler(Crawler):
    base_url = "https://sakuranovel.id/"
    language = "id"

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge: native requests return 403 and the "
        "Playwright browser (headless and headful) never clears 'Just a "
        "moment...'."
    )
