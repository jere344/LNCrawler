# -*- coding: utf-8 -*-
"""novelfr.com — French WordPress site (Kadence theme), registered but disabled.

The WordPress REST API is open, but the only published post is the default
"Hello world!" post, so there is no novel content to crawl yet. Re-check later.
"""

from lncrawl.core.crawler import Crawler


class NovelFrCrawler(Crawler):
    base_url = [
        "https://novelfr.com/",
        "https://www.novelfr.com/",
    ]
    language = "fr"

    is_disabled = True
    disable_reason = (
        "WordPress site with no novel content yet: the only post is the "
        "default 'Hello world!' post. Re-check later."
    )
