# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovelkiCrawler(Crawler):
    base_url = ["https://novelki.pl/"]
    language = "pl"

    is_disabled = True
    disable_reason = (
        "Login-gated Polish novel platform (Laravel API + SPA). Public /api/guest "
        "only returns counts; /api/projects, /api/home and /api/project/{id} answer "
        "'Unauthenticated' to curl. Tested with curl only, not in a real browser."
    )
