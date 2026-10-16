# -*- coding: utf-8 -*-
"""KakaoPage (page.kakao.com). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class KakaoPageCrawler(Crawler):
    base_url = "https://page.kakao.com/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Mostly paid and ticket-based. /main/novel and the API return 403 from outside the app; free-wait chapters need app-level requests.'
