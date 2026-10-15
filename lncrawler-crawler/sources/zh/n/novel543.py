# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class Novel543Crawler(Crawler):
    base_url = "https://www.novel543.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "Cloudflare JS challenge (cf-mitigated: challenge, 403) on every plain "
        "HTTP request; not bypassed. A real browser renders the Traditional "
        "Chinese chapter text passively, but automating that counts as "
        "bot-detection bypass, so this stays disabled."
    )
