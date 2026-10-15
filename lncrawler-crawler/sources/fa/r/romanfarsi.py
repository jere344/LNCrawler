# -*- coding: utf-8 -*-
"""roman-farsi.ir — Persian romance novel download site, disabled.

Novel pages are public (title, author, genre, page count, summary) but the
full text is only offered as a PDF/EPUB/APK download. The page states that
downloads require a site membership ("برای دانلود این رمان باید عضو سایت
شوید"), so there is no free chapter text to crawl.
"""

from lncrawl.core.crawler import Crawler


class RomanFarsiCrawler(Crawler):
    base_url = "https://roman-farsi.ir/"
    language = "fa"

    is_disabled = True
    disable_reason = (
        "Full novel text is only available as a PDF/EPUB download, and the "
        "download is gated behind a site membership; there are no free "
        "chapter pages to crawl."
    )
