# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class BookwalkerTWCrawler(Crawler):
    base_url = "https://www.bookwalker.com.tw/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "E-book store (Taiwan, Kadokawa): paid e-books; free content is limited "
        "to short samples. Purchase/login required for full chapter text."
    )
