# -*- coding: utf-8 -*-
"""ScrollersPub (scrollerspub.com) - free online reader/library for web and light novels.

Disabled: the catalog is an aggregator (about 11,900 titles, mostly mirrored from
lightnovelpub.org, chikari.moe and novelfull.net) and every synopsis is rewritten
by an LLM (synopsis_rewritten = true on 11,873 of 11,878 records). The chapters
are copies of sites already covered (chikari.py, novelfull.py), so crawl those
instead of the mirror.

Tested: curl with a browser UA. The SPA talks to a clean JSON API
(/api/novels, /api/novel/<uuid>/chapters, /api/chapter/<id>/read), so it is not a
bot wall, and the content is workable if this policy is ever relaxed.
"""

from lncrawl.core.crawler import Crawler


class ScrollersPubCrawler(Crawler):
    base_url = [
        "https://scrollerspub.com/",
        "https://www.scrollerspub.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Mirror aggregator of lightnovelpub.org / chikari.moe / novelfull.net (already covered by chikari.py and novelfull.py) with LLM-rewritten synopses"
    )
