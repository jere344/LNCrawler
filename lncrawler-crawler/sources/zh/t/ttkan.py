# -*- coding: utf-8 -*-
"""TTKan (ttkan.co). Disabled: bot wall, see disable_reason."""

from lncrawl.core.crawler import Crawler


class TtkanCrawler(Crawler):
    base_url = "https://www.ttkan.co/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "bot wall: custom gatekeeper challenge; curl 403; headless chromium still on verification at 25s"
    )
