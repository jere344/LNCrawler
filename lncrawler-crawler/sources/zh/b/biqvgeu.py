# -*- coding: utf-8 -*-
"""biqvgeu.cc - Chinese novel library (gb2312, 顶点小说 style layout).

Disabled: the site is alive and book pages expose metadata and chapter
text. However, the book page does not expose a full chapter list, and
the index URL returns 404. The connection also fails intermittently
under HTTP/2 (curl_cffi), so HTTP/1.1 is needed. Not implemented.
"""

from lncrawl.core.crawler import Crawler


class BiqvgeuCrawler(Crawler):
    base_url = "https://www.biqvgeu.cc/"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Chapter list not located on book page (index 404); HTTP/2 connection drops under curl_cffi, needs HTTP/1.1. Not implemented."
