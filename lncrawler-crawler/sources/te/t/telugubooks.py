# -*- coding: utf-8 -*-
"""TeluguBooks.in (Navodaya Book House) - Telugu bookshop.

A Shopify storefront selling printed books and downloadable ebooks/PDFs; the
product pages expose title/author/genre metadata but no chapter text in the
page.  Novel chapters are not readable anonymously, so the source is disabled
rather than shipped as a broken crawler.
"""

from lncrawl.core.crawler import Crawler


class TeluguBooksCrawler(Crawler):
    base_url = ["https://www.telugubooks.in/", "https://telugubooks.in/"]
    language = "te"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Shopify bookstore selling printed books and downloadable ebooks/PDFs; "
        "no anonymously readable chapter text in HTML."
    )
