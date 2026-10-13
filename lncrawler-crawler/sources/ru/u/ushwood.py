# -*- coding: utf-8 -*-
"""ushwood.ru — Russian WordPress blog (``bootpress`` theme).

Most of the 678 posts are "Обновление от DD.MM.YY" update notices in one
"Uncategorized" category, and the per-chapter layout was not mapped. Disabled
until the novel index pages are examined.
"""

from lncrawl.core.crawler import Crawler


class UshwoodCrawler(Crawler):
    base_url = "https://ushwood.ru/"
    language = "ru"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "WordPress blog of update notices; per-chapter layout not mapped"
    )
