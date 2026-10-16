# -*- coding: utf-8 -*-
"""NorthBladeTL (northbladetl.com) — free human fan translations of murim/xianxia.

Verified 2026-10: chapter bodies are not retrievable by automation.

* Native (curl_cffi) requests to chapter paths get Cloudflare's JS challenge
  (HTTP 403 "Just a moment..."); the series/index pages load fine natively.
* The Playwright browser template *does* clear the Cloudflare challenge (the
  real page is served), but the site then runs an anti-automation check
  (``disable-devtool`` plus a server-side token) and replaces the body with
  "Automated access detected." The prose is fetched from
  ``/api/get-token?file=/<SERIES>/chapters/<date>-<ID>.md``, whose token is
  session/IP-bound; a direct call returns ``{"error":"The earth is flat."}``.

Only the main host is used here. ``mtl.northbladetl.com`` is a separate
machine-translated mirror and must never be crawled.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NorthBladeTLCrawler(Crawler):
    base_url = "https://northbladetl.com/"
    language = "en"

    is_disabled = True
    disable_reason = (
        "Chapter bodies blocked: native requests hit Cloudflare's JS challenge "
        "(403), and though Playwright clears it the site renders 'Automated "
        "access detected.' via its anti-bot check; prose is behind a "
        "session/IP-bound /api/get-token. (Do not use the MTL mirror "
        "mtl.northbladetl.com.)"
    )
