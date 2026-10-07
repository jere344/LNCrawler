# -*- coding: utf-8 -*-
"""eLibrary of Cambodia (elibraryofcambodia.org) - Khmer library.

WordPress site of public-domain Khmer ebooks, manuscripts and audiobooks.
Each ebook page only embeds the PDF.js viewer pointed at a PDF upload
(``.../pdfjs/web/file=...pdf``); there is no HTML/EPUB chapter text.  Audio
pages are MP3 only.  The chapter engine cannot read PDF, so disabled rather
than shipped as a broken crawler.
"""

from lncrawl.core.crawler import Crawler


class ELibraryOfCambodiaCrawler(Crawler):
    base_url = ["https://www.elibraryofcambodia.org/", "https://elibraryofcambodia.org/"]
    language = "km"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = "PDF-only, no readable chapters"
