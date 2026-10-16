# -*- coding: utf-8 -*-
"""mitemin.net (Japanese illustration and story sharing). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class MiteminCrawler(Crawler):
    base_url = "https://mitemin.net/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Primarily an illustration-sharing site. Its text is mostly user blogs "
        "(userpageblog, blog.mitemin.net), which are not novel series with chapter "
        "lists. There is no novel-catalogue structure to crawl, so it does not fit "
        "the novel-source model."
    )
