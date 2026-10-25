# -*- coding: utf-8 -*-
"""Berry's Cafe (berrys-cafe.jp). Disabled: Varnish 403 block on every request, see disable_reason."""

from lncrawl.core.crawler import Crawler


class BerrysCafeCrawler(Crawler):
    base_url = ["https://www.berrys-cafe.jp/", "https://berrys-cafe.jp/"]
    language = "ja"

    is_disabled = True
    disable_reason = (
        "Varnish 403 (error 54113) on every request, bare host answers 425 under curl_cffi; "
        "tested with curl, curl_cffi chrome and safari impersonation, and the real browser pane"
    )
