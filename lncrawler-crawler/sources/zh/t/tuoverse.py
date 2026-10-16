# -*- coding: utf-8 -*-
"""沱书·文存 (tuoverse.com). Disabled: reader is whole-book pagination, see disable_reason."""

from lncrawl.core.crawler import Crawler


class TuoverseCrawler(Crawler):
    base_url = "https://tuoverse.com/"
    language = "zh"

    is_disabled = True
    disable_reason = (
        "no chapter-level reader: /novel/<id>/chapter-N.html is page N of the whole book "
        "(fixed ~4000-char slices, '第N页', 50 pages for 画江湖之帝姬（gl）), chapter breaks "
        "exist only as in-text 第X章 headings that cross page boundaries. "
        "Tested with curl only (no bot wall): home, /novel/03194f2b/, chapter-1..chapter-50; "
        "/search/?q=江湖 returned no novel links. Stitching pages into chapters is a possible follow-up."
    )
