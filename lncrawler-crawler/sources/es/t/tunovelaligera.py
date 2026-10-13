# -*- coding: utf-8 -*-
"""tunovelaligera.com — Spanish light-novel site, registered but disabled.

Every request answers with HTTP 403 and a Cloudflare "Just a moment..."
challenge, so no page can be read without clearing that challenge first.
"""

from lncrawl.core.crawler import Crawler


class TuNovelaLigeraCrawler(Crawler):
    base_url = [
        "https://tunovelaligera.com/",
        "https://www.tunovelaligera.com/",
    ]
    language = "es"

    is_disabled = True
    disable_reason = (
        "Cloudflare bot challenge (HTTP 403 'Just a moment...') on every path. "
        "Needs a browser or solving service that can clear the challenge."
    )
