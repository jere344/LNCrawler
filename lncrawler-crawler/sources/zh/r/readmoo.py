# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class ReadmooCrawler(Crawler):
    base_url = "https://www.readmoo.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "E-book store (Taiwan): book bodies are paid; only short free samples "
        "exist. Login/purchase required for full chapters."
    )
