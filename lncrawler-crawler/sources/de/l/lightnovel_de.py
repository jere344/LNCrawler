# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class LightNovelDeCrawler(Crawler):
    base_url = ["https://lightnovel.de/", "https://www.lightnovel.de/"]
    language = "de"

    is_disabled = True
    disable_reason = (
        "Commercial German publisher and shop (TOKYOPOP DE). Chapter previews are "
        "page images on fliphtml5, with no free chapter text. Tested with curl only."
    )
