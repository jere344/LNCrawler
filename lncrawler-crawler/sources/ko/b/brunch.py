# -*- coding: utf-8 -*-
"""Brunch (brunch.co.kr). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class BrunchCrawler(Crawler):
    base_url = "https://brunch.co.kr/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Requires login for most pages: the root redirects to the Kakao login.'
