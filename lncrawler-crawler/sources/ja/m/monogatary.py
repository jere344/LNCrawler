# -*- coding: utf-8 -*-
"""monogatary.com (Japanese interactive story platform). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class MonogataryCrawler(Crawler):
    base_url = "https://monogatary.com/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Interactive story-game platform ('みんなで遊べるストーリーエンタテインメント'). "
        "The root returns a 200 React shell with no server-rendered story text or "
        "novel links. Chapter content is served by a client-side API that was not "
        "reverse-engineered, and the platform is a choose-your-path format that does "
        "not map onto linear chapters."
    )
