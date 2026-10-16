# -*- coding: utf-8 -*-
"""My Library Myanmar (myanbooklibrary.blogspot.com) - Burmese ebooks.

A Blogger site whose posts are catalogue pages of ebook download links
(mediafire / yadi.sk / write.as).  Every book is a PDF; no post carries
readable chapter text or an EPUB, so the chapter engine cannot read it.
Disabled rather than shipped as a broken crawler.
"""

from lncrawl.core.crawler import Crawler


class MyLibraryMyanmarCrawler(Crawler):
    base_url = "https://myanbooklibrary.blogspot.com/"
    language = "my"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = "PDF-only, no readable chapters"
