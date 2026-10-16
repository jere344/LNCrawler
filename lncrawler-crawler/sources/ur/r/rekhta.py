# -*- coding: utf-8 -*-
"""Rekhta (rekhta.org) — Urdu poetry and books library.

Disabled: the ebook reader gates page text behind a registration and captcha
flow ("You have exhausted 5 free content pages per year"). The reader's
``/EbookData/GetEbookFromApi/?bkId=<uuid>&pgIdx=<n>`` endpoint returns an empty
string for every page index when anonymous, checked on two different ebooks,
so no chapter text is reachable without an account.
"""

from lncrawl.core.crawler import Crawler


class RekhtaCrawler(Crawler):
    base_url = ["https://www.rekhta.org/", "https://rekhta.org/"]
    language = "ur"
    is_disabled = True
    disable_reason = (
        "Rekhta's ebook reader requires registration/captcha after a few free "
        "pages; anonymous page text requests return empty content."
    )
