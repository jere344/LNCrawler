# -*- coding: utf-8 -*-
"""Xsbiquge (xsbiquge.la). Disabled: region/IP block on every request, see disable_reason."""

from lncrawl.core.crawler import Crawler


class XsbiqugeCrawler(Crawler):
    base_url = "https://www.xsbiquge.la/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "403 Forbidden 'The region has been denied' on every path (IP/region block, not a challenge); "
        "tested with curl, curl_cffi chrome and safari impersonation, and the real browser pane"
    )
