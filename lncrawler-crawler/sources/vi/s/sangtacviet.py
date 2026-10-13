# -*- coding: utf-8 -*-
"""SangTacViet - disabled source.

Disabled: Chapter list is loaded by JS and returns empty without a browser session; chapter text is AES-encrypted client-side; login/Cloudflare flow. Not workable with plain HTTP.
"""

from lncrawl.core.crawler import Crawler


class SangTacVietCrawler(Crawler):
    base_url = "https://sangtacviet.vip/"
    language = "vi"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Chapter list is loaded by JS and returns empty without a browser session; chapter text is AES-encrypted client-side; login/Cloudflare flow. Not workable with plain HTTP'
