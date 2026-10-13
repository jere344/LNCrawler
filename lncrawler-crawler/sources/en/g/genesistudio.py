# -*- coding: utf-8 -*-
"""Genesis Studio (genesistudio.com). Disabled: Original English fiction platform (not translations) with a private Next.js API."""

from lncrawl.core.crawler import Crawler


class GenesisStudioCrawler(Crawler):
    base_url = [
        "https://genesistudio.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Original English fiction platform (not translations) with a private Next.js API; out of scope"
    )
