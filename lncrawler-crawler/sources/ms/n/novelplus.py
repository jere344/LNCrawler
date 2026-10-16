# -*- coding: utf-8 -*-
"""NovelPlus - disabled source.

Disabled: Domain unreachable from the research host; freemium app plus web reader with a paid ad-free tier; no open catalogue or chapter endpoint verified.
"""

from lncrawl.core.crawler import Crawler


class NovelPlusCrawler(Crawler):
    base_url = [
        "https://novelplus.my/",
        "https://novelplus.com/",
    ]
    language = "ms"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Domain unreachable from the research host; freemium app plus web reader with a paid ad-free tier; no open catalogue or chapter endpoint verified'
