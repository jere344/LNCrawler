# -*- coding: utf-8 -*-
from lncrawl.core.crawler import Crawler


class HamelnCrawler(Crawler):
    """Hameln (syosetu.org), a major original/fanfic Japanese web-novel site.

    Every path (including robots.txt) answers HTTP 403 with a Cloudflare JS
    challenge. Neither the native curl_cffi backend nor Playwright (headless
    or headed under Xvfb, bundled Chromium) is issued a cf_clearance cookie
    from the crawler host, so the challenge cannot be solved here.
    """

    base_url = "https://syosetu.org/"
    language = "ja"

    is_disabled = True
    disable_reason = (
        "Cloudflare JS challenge on every path; not solvable from the crawler "
        "host with curl_cffi or Playwright (no cf_clearance issued)."
    )
