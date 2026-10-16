# -*- coding: utf-8 -*-
"""Postype (postype.com). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class PostypeCrawler(Crawler):
    base_url = "https://www.postype.com/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Creator platform mixing paid and free posts. No stable public novel listing; series pages are platform guides and post content is client-rendered.'
