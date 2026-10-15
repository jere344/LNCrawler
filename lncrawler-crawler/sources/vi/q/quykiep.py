# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class QuyKiepCrawler(Crawler):
    base_url = "https://quykiep.com/"
    language = "vi"

    is_disabled = True
    disable_reason = (
        "Chapter list is gated behind a per-visitor verification code "
        "(a 'download code' fetched from be-traffic.truyenchuhay.org and "
        "entered in a modal) before any chapter is listed. Chapter entries "
        "have no href and no open API route was found, so the chapter bodies "
        "are not reachable over plain HTTP."
    )
