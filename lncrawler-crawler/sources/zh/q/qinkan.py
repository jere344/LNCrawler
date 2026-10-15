# -*- coding: utf-8 -*-
"""Qinkan (请看小说网 / 奇书网, www.qinkan.net) - Chinese novel download site.

Static GBK site. Each book page offers whole-book files only (TXT, EPUB, MOBI,
AZW3) at ``https://d3.qinkan.net/d/txt/<cls>/<title>_qinkan.net.txt``; there
are no per-chapter pages. Splitting the TXT into chapters by its ``第X章``
headings was tested on 11 books and is not reliable (headings with gaps and
duplicate numbers, volume markers mixed in, no headings at all in some books,
and GBK-unmappable characters replaced by ``?``), so this source is disabled.
"""

from lncrawl.core.crawler import Crawler


class QinkanCrawler(Crawler):
    base_url = ["https://www.qinkan.net/", "https://qinkan.net/"]
    language = "zh"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "(Site serves whole-book TXT/EPUB/MOBI files only, no per-chapter pages; "
        "splitting the TXT by 第X章 headings is unreliable: tested on 11 books, "
        "with gaps, duplicate numbers, volume markers mixed in, no headings in some, "
        "and GBK-unmappable characters; tested with plain HTTP only, no browser)"
    )
