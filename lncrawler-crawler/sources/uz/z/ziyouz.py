# -*- coding: utf-8 -*-
"""Ziyouz.com (Uzbek) library at n.ziyouz.com.

The Joomla library lists each work as Phoca Download files
(``/kutubxona/category/<id>-<slug>?download=<id>:<name>``). Every file checked
across the library categories is a PDF scan or an MP3 audiobook, with no
readable web chapters. Sampled: "Barcha kitoblar", "O'zbek nasri" and
"O'zbek zamonaviy she'riyati" (PDF), plus an audiobook item (MP3).

The source is kept disabled until the site offers chapter text on the web.
"""

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException


class ZiyouzCrawler(Crawler):
    base_url = "https://n.ziyouz.com/"
    language = "uz"
    is_disabled = True
    disable_reason = (
        "n.ziyouz.com only serves works as downloadable PDF or MP3 files "
        "(Phoca Download); there is no readable web chapter text to crawl."
    )

    def read_novel_info(self) -> None:
        raise LNException(self.disable_reason)
