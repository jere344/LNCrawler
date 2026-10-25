# -*- coding: utf-8 -*-
"""Just Light Novels (justlightnovels.com). Disabled: Cloudflare challenge on every URL."""

from lncrawl.core.crawler import Crawler


class JustLightNovelsCrawler(Crawler):
    base_url = [
        "https://justlightnovels.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge on every URL: home, robots.txt, sitemap, wp-json and novel pages "
        "with curl_cffi scraper; headless Chromium also stuck on Just a moment; no readable chapter HTML verified"
    )
