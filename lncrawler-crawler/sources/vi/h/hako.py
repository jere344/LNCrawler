# -*- coding: utf-8 -*-
"""Hako (ln.hako.vn, alias docln.net) — Vietnamese light novel library.

Human-translated light novels with a large catalog, so worth revisiting
(high value) if a session-cookie approach can get past the challenge.

Disabled: Cloudflare managed challenge on both hosts. The crawler's scraper
(curl_cffi Chrome impersonation) gets 403 with the "Just a moment..." page
(cf-mitigated: challenge) on https://ln.hako.vn/ and https://docln.net/. A
real browser also stayed on "Just a moment" for about 20 s and never cleared.
"""

from lncrawl.core.crawler import Crawler


class HakoCrawler(Crawler):
    base_url = ["https://ln.hako.vn/", "https://docln.net/"]
    language = "vi"
    is_disabled = True
    disable_reason = "Cloudflare challenge on ln.hako.vn and docln.net; scraper gets 403, browser stuck"
