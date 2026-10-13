# -*- coding: utf-8 -*-
"""Naver Series (series.naver.com/novel). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class NaverSeriesCrawler(Crawler):
    base_url = "https://series.naver.com/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Body text is not in the HTML: reading goes through launchViewer and the nstore viewer. Free episodes need a login-gated ticket action; the sampled title was paid.'
