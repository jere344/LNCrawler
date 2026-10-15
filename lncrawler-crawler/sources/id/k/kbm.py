# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class KbmCrawler(Crawler):
    base_url = "https://kbm.id/"
    language = "id"

    is_disabled = True
    disable_reason = (
        "Cloudflare-fronted; detail URL tokens are client-side encrypted "
        "with crypto-js; chapter bodies are behind a coin paywall. "
        "Tested with curl only, not in a real browser."
    )
