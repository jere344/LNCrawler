# -*- coding: utf-8 -*-
"""PurrFiction (purrfiction.io, alias neovel.io) — English web novel site.

Disabled: JavaScript-only single-page app. https://purrfiction.io/ and
https://neovel.io/ (which redirects to purrfiction.io) return a static shell
with only "Please enable JavaScript to continue using this application" and
no novel data in the HTML. The site's backing API was not looked for.
"""

from lncrawl.core.crawler import Crawler


class PurrFictionCrawler(Crawler):
    base_url = ["https://purrfiction.io/", "https://neovel.io/"]
    language = "en"
    is_disabled = True
    disable_reason = "JavaScript-only SPA; static HTML has no novel data, backing API not investigated"
