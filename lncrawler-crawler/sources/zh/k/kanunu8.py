# -*- coding: utf-8 -*-
"""kanunu8.com - classic and translated literature download site.

Disabled: out of scope for web novels. Only the homepage was checked; it is a
download catalog rather than a chapter reader.
"""

from lncrawl.core.crawler import Crawler


class Kanunu8Crawler(Crawler):
    base_url = "https://www.kanunu8.com"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Classic/translated literature download site, out of scope; not investigated beyond homepage."
