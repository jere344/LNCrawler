# -*- coding: utf-8 -*-
"""novelasmtl.com — Spanish machine-translated (MTL) novels on Blogger.

Intentionally excluded: MTL content is extremely low quality. Registered as a
disabled stub only; no crawling code is shipped for this site.
"""

from lncrawl.core.crawler import Crawler


class NovelasMtlCrawler(Crawler):
    base_url = [
        "https://www.novelasmtl.com/",
        "https://novelasmtl.com/",
    ]
    language = "es"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
