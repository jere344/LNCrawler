# -*- coding: utf-8 -*-
"""Fictionlog (fictionlog.co) - major Thai licensed/official translation platform.

The whole site (including ``/api/...``) sits behind a Cloudflare Turnstile
interactive challenge: curl_cffi gets HTTP 403 and a headless Chromium stays on
the "Just a moment..." page indefinitely, so neither the native nor the browser
backend can reach the content.  There is no reachable public API host
(``api.fictionlog.co`` does not resolve).  Disabled until a Cloudflare-capable
fetch (residential proxy / challenge solver) is available.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class FictionlogCrawler(Crawler):
    base_url = [
        "https://fictionlog.co/",
        "https://www.fictionlog.co/",
    ]
    language = "th"
    has_manga = False
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Cloudflare Turnstile interactive challenge on the whole site: native "
        "requests get HTTP 403 and headless Chromium never clears the challenge; "
        "no public API."
    )
