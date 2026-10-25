# -*- coding: utf-8 -*-
"""Novema (novema.jp). Disabled: Varnish 403 block on every request, see disable_reason."""

from lncrawl.core.crawler import Crawler


class NovemaCrawler(Crawler):
    base_url = "https://novema.jp/"
    language = "ja"

    is_disabled = True
    disable_reason = (
        "Varnish 403 (error 54113) on every request, no challenge page to solve; "
        "tested with curl, curl_cffi chrome and safari impersonation, and the real browser pane"
    )
