# -*- coding: utf-8 -*-
"""17k.com - Chinese web novel platform.

Disabled: book and chapter pages are behind an Aliyun WAF JavaScript
challenge (renderData textarea). Plain HTTP and curl_cffi chrome
impersonation both receive the challenge page. A headless-browser
implementation was not attempted.
"""

from lncrawl.core.crawler import Crawler


class Crawler17k(Crawler):
    base_url = "https://www.17k.com/"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Aliyun WAF JS challenge on book and chapter pages; blocked under curl_cffi impersonation. Requires a browser-based crawler."
