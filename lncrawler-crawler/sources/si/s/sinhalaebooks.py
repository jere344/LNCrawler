# -*- coding: utf-8 -*-
"""Sinhala Ebooks (sinhalaebooks.com) - Sinhala ebook downloads.

WordPress site hosting scanned Sinhala novels.  Each book page only carries
metadata (title/author, file format/size) plus a link to a PDF on an external
host (e.g. MediaFire); the text is never rendered in the page.  The chapter
engine cannot read PDFs, so the source is disabled.
"""

from lncrawl.core.crawler import Crawler


class SinhalaEbooksCrawler(Crawler):
    base_url = ["https://www.sinhalaebooks.com/", "https://sinhalaebooks.com/"]
    language = "si"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "PDF download links only (scanned novels hosted off-site, e.g. "
        "MediaFire); no readable chapter text."
    )
