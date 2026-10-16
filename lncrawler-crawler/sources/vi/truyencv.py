# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class TruyenCVCrawler(Crawler):
    base_url = "https://truyencv.com/"
    language = "vi"

    is_disabled = True
    disable_reason = (
        "Site permanently closed on 2026-02-10; every URL serves only a "
        "goodbye page (the successor host is also gone)."
    )
