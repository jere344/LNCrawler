# -*- coding: utf-8 -*-
"""Joara (joara.com). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class JoaraCrawler(Crawler):
    base_url = "https://www.joara.com/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Client-side SPA (same shell for every route). The API at api.joara.com needs signed app requests; the bundled web key is rejected from outside the app. Not workable as a static source.'
