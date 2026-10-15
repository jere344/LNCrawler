# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class CabacaCrawler(Crawler):
    base_url = "https://cabaca.id/"
    language = "id"

    is_disabled = True
    disable_reason = (
        "Cordova app backed by a DreamFactory API (jj.cabaca.id/api/v2). "
        "Database endpoints return 500 'could not find driver'; the data "
        "needs the embedded app key plus a session token. Tested with curl only."
    )
