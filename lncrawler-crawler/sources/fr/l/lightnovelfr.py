# -*- coding: utf-8 -*-
"""lightnovelfr.com — French light-novel site, registered but disabled.

Every request redirects to a JavaScript challenge (a JWT token is passed in the
URL), so no page can be fetched with plain HTTP. The challenge needs JavaScript
execution before any content is reachable.
"""

from lncrawl.core.crawler import Crawler


class LightNovelFrCrawler(Crawler):
    base_url = [
        "https://lightnovelfr.com/",
        "https://www.lightnovelfr.com/",
    ]
    language = "fr"

    is_disabled = True
    disable_reason = (
        "Every request redirects to a JavaScript challenge (JWT token in the "
        "URL). Needs JavaScript execution before any content is reachable."
    )
