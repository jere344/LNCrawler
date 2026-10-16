# -*- coding: utf-8 -*-
"""maho.jp (魔法のiらんど). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class MahoCrawler(Crawler):
    base_url = "https://maho.jp/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Next.js app. /ranking returns 200, but novel ranking and list data come from a client-side API that was not identified.'
