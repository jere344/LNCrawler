# -*- coding: utf-8 -*-
"""Tunwalai (tunwalai.com) - major Thai novel platform by Ookbee.

The whole site sits behind a Cloudflare interactive challenge.  The native
TLS-impersonating client gets HTTP 403 and a headless Chromium never clears the
Turnstile "Just a moment..." page, so neither scraping path works.  There is no
reachable public JSON API host (api.tunwalai.com does not resolve).  Disabled
until a Cloudflare-capable fetch (residential proxy / challenge solver) exists.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class TunwalaiCrawler(Crawler):
    base_url = ["https://tunwalai.com/", "https://www.tunwalai.com/"]
    language = "th"

    is_disabled = True
    disable_reason = (
        "Cloudflare interactive challenge (Turnstile): native requests get HTTP "
        "403 and headless Chromium never clears the challenge; no public API."
    )
