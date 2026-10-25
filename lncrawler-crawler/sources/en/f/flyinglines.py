# -*- coding: utf-8 -*-
"""Flying Lines (flying-lines.com). Disabled: chapters after the free preview are locked behind SP currency; bodies come from a signed API POST."""

from lncrawl.core.crawler import Crawler


class FlyingLinesCrawler(Crawler):
    base_url = [
        "https://www.flying-lines.com/",
        "https://flying-lines.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Chapters 5 onward, 33 of 37 on the tested novel, are locked behind SP currency; their bodies come from a request signed with a key in the site script, which is not reproduced here"
    )
