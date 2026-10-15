# -*- coding: utf-8 -*-
"""Ridibooks (ridibooks.com, Korean paid novels). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class RidibooksCrawler(Crawler):
    base_url = "https://ridibooks.com/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Paid platform, mostly purchase-gated text. Plain curl returns 403 with "
        "'cf-mitigated: challenge' (Cloudflare JS challenge) on the root and the "
        "novel pages, so static HTTP scraping is blocked. novel.ridibooks.com did "
        "not connect (curl 000). Tested with curl only; a real browser session was "
        "not tried, so the decision is provisional."
    )
