# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class Novel8Crawler(Crawler):
    base_url = "https://www.8novel.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "Chapter bodies are not in the HTML. They are fetched by obfuscated "
        "client-side JS (/js/read.js and inline scrambled $.get URL builder) "
        "that decodes the text in the browser; too complex for plain HTTP. "
        "Tested with curl only (book, chapter and read.js pages all 200)."
    )
