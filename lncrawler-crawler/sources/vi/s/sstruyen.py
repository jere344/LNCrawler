# -*- coding: utf-8 -*-
"""SStruyen (sstruyen.vn) — Vietnamese web novel site.

Disabled: the crawler's scraper gets 403 on https://sstruyen.vn/ with a
Cloudflare page titled "DNS points to prohibited IP", which is a Cloudflare
block rather than a JavaScript challenge. Not checked in a real browser.

MTL status is unchecked: the site was not reviewed for machine-translated
content, so it may also fall under the MTL exclusion.
"""

from lncrawl.core.crawler import Crawler


class SstruyenCrawler(Crawler):
    base_url = ["https://sstruyen.vn/"]
    language = "vi"
    is_disabled = True
    disable_reason = "Cloudflare 403 (DNS points to prohibited IP) via scraper; not checked in a browser"
