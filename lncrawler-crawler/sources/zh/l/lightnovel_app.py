# -*- coding: utf-8 -*-
"""lightnovel.app - Chinese-language Vue SPA. Disabled: Chinese-language Vue SPA."""

from lncrawl.core.crawler import Crawler


class LightNovelAppCrawler(Crawler):
    base_url = [
        "https://lightnovel.app/",
    ]
    language = "zh"

    is_disabled = True
    disable_reason = (
        "Chinese-language Vue SPA; out of scope for the English group"
    )
